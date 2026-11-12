from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import threading
from types import MappingProxyType, SimpleNamespace

import pytest

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import (
    AdmissionOutcome, AuthorityClass, ControlPlaneKernel,
)
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_model_authority import build_local_model_authority_map
from sentientos.local_model_production_serving import ProductionServingController, ServingSession
from sentientos.local_model_serving_inference import (
    ProductionServingInferenceController,
    ProductionServingInferenceError,
)
from sentientos.foreground_game_bridge import (
    BridgeForegroundGameDetector,
    WindowsForegroundBridgePublisher,
)
from sentientos.foreground_game_detection import ForegroundGameObservation
from sentientos.gaming_companion_bridge import CompanionBridgeReceiver
from sentientos.gaming_companion_bridge_runtime import (
    CompanionBridgeLoopbackClient,
    CompanionBridgeLoopbackRuntime,
)
from sentientos.gaming_companion_tls_transport import (
    CompanionBridgeMutualTLSClient,
    CompanionBridgeMutualTLSRuntime,
)
from sentientos.game_performance_bridge import (
    GamePerformanceBridgeDetector,
    WindowsGamePerformanceBridgePublisher,
)
from sentientos.local_model_resource_profile import (
    LLAMA_CPP_RESOURCE_PROFILE_SCHEMA,
    llama_cpp_resource_profile_digest,
)
from sentientos.local_runtime_provisioning import semantic_digest
from sentientos.runtime_governor import RuntimeGovernor
from sentientos.host_collectors import HostCollectorResult
from sentientos.host_resource_runtime import (
    HostObservationCollectorSpec, HostResourceRuntimeCoordinator,
    build_observation_plan,
)
from sentientos.windows_game_performance import WindowsGamePerformanceObserver

pytestmark = pytest.mark.no_legacy_skip


def test_mtls_game_evidence_and_host_pressure_defer_then_govern_optional_model_release(
        monkeypatch, tmp_path, request):
    """Join authenticated game samples to host-pressure admission and release."""
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding
    from tests.test_gaming_companion_tls_transport import _certificate_bundle

    now = datetime.now(timezone.utc)
    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    server_certificate = x509.load_pem_x509_certificate(
        (tmp_path / "server.pem").read_bytes())
    server_pin = hashlib.sha256(server_certificate.public_bytes(Encoding.DER)).hexdigest()
    source_key = b"authenticated-game-resource-source-key"
    ack_key = b"authenticated-core-resource-ack-key-32"
    source_id, generation_id = "windows-edge", "edge-resource-generation-1"
    runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1", port=0,
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=CompanionBridgeReceiver(source_keys={source_id: source_key},
            expected_generations={source_id: generation_id}),
        acknowledgment_source_id="wsl-core",
        acknowledgment_generation_id="core-resource-generation-1",
        acknowledgment_key=ack_key)
    port = runtime.start()
    request.addfinalizer(runtime.close)
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core": ack_key},
            expected_generations={"wsl-core": "core-resource-generation-1"}),
        expected_server_certificate_sha256=server_pin)

    class GamePresenceSample:
        def observe(self, process_names):
            assert tuple(process_names) == ("examplegame.exe",)
            return ForegroundGameObservation("available", True,
                hashlib.sha256(b"examplegame.exe").hexdigest(), now.isoformat())

    presence_publisher = WindowsForegroundBridgePublisher(
        detector=GamePresenceSample(), client=client, source_id=source_id,
        session_id="game-presence-session", generation_id=generation_id,
        source_key=source_key)
    presence_message = presence_publisher.publish_once(("examplegame.exe",))
    performance_publisher = WindowsGamePerformanceBridgePublisher(
        observer=WindowsGamePerformanceObserver(
            system_provider=lambda: "Windows",
            process_provider=lambda _pid: {"name": "examplegame.exe",
                "cpu_percent": 15.0, "rss_bytes": 8192},
            frame_provider=lambda _pid: ((), None),
            clock=lambda: now.isoformat()),
        client=client, source_id=source_id, session_id="game-performance-session",
        generation_id=generation_id, source_key=source_key, process_id=4012)
    performance_message = performance_publisher.publish_once()

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=source_id,
        generation_id=generation_id, clock=lambda: now)
    detector.set_game_workload_admission_owner(kernel)
    detector.set_game_performance_admission_owner(kernel)

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_plan = build_observation_plan(specs=[
        HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
            collector("cpu", utilization_percent=95.0)),
        HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
            collector("memory", used_percent=40.0)),
        HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
            collector("nvidia_gpu", device_count=0, devices=[])),
    ])
    host_resource_owner = HostResourceRuntimeCoordinator(
        kernel=kernel, runtime_state_root=tmp_path / "host-resource",
        plan=host_plan, clock=lambda: now.isoformat())
    bridge, serving, _, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, foreground_game_detector=detector,
        host_resource_observation_owner=host_resource_owner)
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
    try:
        prompt = ("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
            "[SESSION_HISTORY_DATA]\nUSER_DATA: hello")
        receipt = bridge.generate(prompt=prompt, caller="chat_service",
            correlation_id="mtls-game-host-pressure")
        assert receipt.status == "deferred"
        assert model.calls == 0
        assert model.closed is True
        assert serving.current_session() is None
        workload = receipt.request["linkage"]["workload_evidence"]
        assert workload["transport_provenance"]["message_id"] == (
            presence_message.payload["message_id"])
        decisions = [json.loads(line) for line in (tmp_path / "kernel-decisions.jsonl").read_text(
            encoding="utf-8").splitlines()]
        inference_decision = next(item for item in decisions
            if item.get("action_kind") == "local_model_inference")
        delegated = inference_decision["delegated_outcomes"]["runtime_governor"]
        assert delegated["reason"] == (
            "deferred_local_model_inference_under_host_pressure_during_game")
        assert delegated["evidence_refs"]["game_performance_evidence"]["message_id"] == (
            performance_message.payload["message_id"])
        assert delegated["evidence_refs"]["game_workload_evidence"]["message_id"] == (
            presence_message.payload["message_id"])
        assert delegated["evidence_refs"]["host_resource_evidence"]["report_id"] == (
            receipt.request["linkage"]["host_resource_observation"]["report_id"])
        assert delegated["evidence_refs"]["observed_pressure_labels"] == ["cpu_pressure"]
        assert host_resource_owner.collector_call_count == 6
        release_files = list((tmp_path / "state" / "installations" / "install-1" /
            "state" / "local-model" / "serving" / "resource-release-receipts").glob("*.json"))
        assert len(release_files) == 1
        release = json.loads(release_files[0].read_text(encoding="utf-8"))
        assert release["status"] == "worker_closed"
        assert release["inference_performed"] is False
        assert release["host_mutation_performed"] is False
        assert release["resource_measurement_comparison"]["status"] == (
            "insufficient_gpu_measurements")
        assert release["resource_measurement_comparison"]["interpretation"] == (
            "sample_delta_only; telemetry_does_not_establish_causation")
    finally:
        detector.close()
        serving.close()


class Kernel:
    def __init__(self, inference=AdmissionOutcome.ALLOW):
        self.inference, self.requests = inference, []

    def admit(self, request):
        self.requests.append(request)
        outcome = self.inference if request.authority_class is AuthorityClass.LOCAL_MODEL_INFERENCE else AdmissionOutcome.ALLOW
        return SimpleNamespace(outcome=outcome, allowed=outcome is AdmissionOutcome.ALLOW,
            authority_class=request.authority_class, actor=request.actor, action_kind=request.action_kind,
            target_subsystem=request.target_subsystem, correlation_id=request.metadata["correlation_id"],
            reason_codes=("test_denial",) if outcome is not AdmissionOutcome.ALLOW else (),
            admission_decision_ref=f"{request.authority_class.value}:{request.metadata['correlation_id']}",
            to_dict=lambda: {"outcome": outcome.value})


class Model:
    supports_per_invocation_thread_limit = True

    def __init__(self, identity, on_generate=None):
        self.active_identity, self.calls, self.closed, self.on_generate = identity, 0, False, on_generate
        self.prompts = []
        self.generation_parameters = []

    def generate(self, prompt, **kwargs):
        self.calls += 1
        self.prompts.append(prompt)
        self.generation_parameters.append(dict(kwargs))
        if self.on_generate: self.on_generate()
        return "answer"

    def close(self): self.closed = True


def setup(monkeypatch, tmp_path, *, inference=AdmissionOutcome.ALLOW, on_generate=None,
          installation_identity="install-1", runtime_handoff_id=None, state_root=None,
          serving_operation_id="serve-1", foreground_game_detector=None,
          kernel_override=None, host_resource_observation_owner=None, gpu_layers=0):
    tmp_path.mkdir(parents=True, exist_ok=True)
    artifact = tmp_path / "exact.gguf"; artifact.write_bytes(b"tiny-model")
    load = {"n_ctx": 512, "n_gpu_layers": gpu_layers}
    config = ModelConfig([ModelCandidate(artifact, "llama_cpp", "catalog-model", {"gpu_layers": gpu_layers})],
        default_engine="llama_cpp", max_context_tokens=512,
        generation=GenerationConfig(max_new_tokens=8, temperature=0, top_p=1))
    authority = build_local_model_authority_map(config, allowed_roots=[tmp_path], observed_at="1970-01-01T00:00:00+00:00")
    record = authority.records[0]
    identity = ActiveModelIdentity(engine=record.engine,
        resolved_artifact_path=str(artifact.resolve()), semantic_artifact_identity=record.semantic_artifact_identity,
        model_content_sha256=record.model_content_sha256, artifact_size_bytes=record.artifact_size_bytes,
        sidecar_metadata_digest=record.sidecar_metadata_digest, configuration_digest=record.configuration_digest,
        candidate_index=0, posture="production", fallback=False)
    state = {"installation_identity": installation_identity, "generation": 1, "model_id": "catalog-model",
        "artifact_id": "artifact-1", "artifact_path": str(artifact), "artifact_sha256": record.model_content_sha256,
        "artifact_size_bytes": record.artifact_size_bytes, "route_id": "route-1", "runtime_id": "runtime-1",
        "interpreter_path": "/runtime/python", "load_configuration": load,
        "authority_map_digest": authority.map_digest, "commissioning_receipt_id": "commissioning-1",
        "commissioning_receipt_semantic_digest": "commissioning-digest"}
    state["state_semantic_digest"] = semantic_digest(state)
    evidence = {"active_state": state, "activation_receipt": {"receipt_id": "activation-1",
        "receipt_semantic_digest": "activation-digest", "resulting_state_digest": state["state_semantic_digest"],
        "expected_prior_activation_state": "ABSENT", "observed_prior_activation_state": "ABSENT"},
        "activation_history": [{"receipt_id": "activation-1"}],
        "catalog_proof": {"proof_semantic_digest": "proof-digest"}}
    current = [evidence]
    monkeypatch.setattr("sentientos.local_model_production_serving.verify_current_activation", lambda *a, **k: current[0])
    handle = InstallationStateRegistry(state_root or (tmp_path / "state"), _test_only=True).open(
        InstallationIdentity.parse(installation_identity), create=True)
    kernel, model = kernel_override or Kernel(inference), Model(identity, on_generate)
    serving = ProductionServingController(handle, kernel, model_factory=lambda c, l: model)
    monkeypatch.setattr(serving, "_commissioning_identity", lambda s: identity.to_dict())
    session = serving.establish(operation_id=serving_operation_id)
    return ProductionServingInferenceController(
        serving, runtime_handoff_id=runtime_handoff_id,
        foreground_game_detector=foreground_game_detector,
        host_resource_observation_owner=host_resource_observation_owner), serving, session, model, kernel, current


def test_exact_serving_backed_generation_has_independent_admission_and_linkage(monkeypatch, tmp_path):
    bridge, serving, session, model, kernel, _ = setup(monkeypatch, tmp_path)
    receipt = bridge.generate(prompt="hello", caller="operator", correlation_id="inference-1")
    assert receipt.status == "admitted_completed" and receipt.output_text == "answer" and model.calls == 1
    assert receipt.admission_decision_ref != session.binding["model_serving_admission_ref"]
    linkage = receipt.request["linkage"]
    for key in ("serving_session_id", "serving_operation_id", "activation_state_semantic_digest",
                "activation_generation", "model_serving_admission_ref", "authority_map_digest",
                "observed_loaded_model_identity"):
        assert key in linkage
    assert [r.authority_class for r in kernel.requests] == [AuthorityClass.MODEL_SERVING, AuthorityClass.LOCAL_MODEL_INFERENCE]
    assert serving.current_session() == session


def test_production_cancellation_reaches_active_governed_invocation(monkeypatch, tmp_path):
    started = threading.Event()
    cancelled = threading.Event()

    def generate_until_cancelled():
        started.set()
        if not cancelled.wait(timeout=5):
            raise AssertionError("cancellation hook was not called")
        raise RuntimeError("fixture_generation_cancelled")

    bridge, serving, _, model, _, _ = setup(
        monkeypatch, tmp_path, on_generate=generate_until_cancelled)
    model.cancel_pending_generation = lambda: (cancelled.set() or True)
    results = {}

    def invoke():
        results["receipt"] = bridge.generate(
            prompt="long work", caller="operator", correlation_id="cancel-active")

    worker = threading.Thread(target=invoke)
    worker.start()
    assert started.wait(timeout=5)

    assert bridge.cancel_pending_generation() is True
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert results["receipt"].status == "cancelled"
    assert results["receipt"].output_text is None
    assert bridge.cancel_pending_generation() is False
    assert serving.current_session() is not None
    serving.close()


def test_resource_reconciliation_accelerates_only_during_automatic_inference(
        monkeypatch, tmp_path):
    started = threading.Event()
    finish = threading.Event()

    def wait_for_release():
        started.set()
        if not finish.wait(timeout=5):
            raise AssertionError("fixture inference release timed out")
        return "answer"

    bridge, serving, _, _, _, _ = setup(
        monkeypatch, tmp_path, on_generate=wait_for_release)
    wakeup = threading.Event()
    bridge.set_resource_reconciliation_wakeup(wakeup.set)
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
    assert wakeup.wait(timeout=1)
    wakeup.clear()
    assert bridge.resource_reconciliation_interval_seconds() == 5.0
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault("receipt", bridge.generate(
        prompt=("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
            "[SESSION_HISTORY_DATA]\nUSER_DATA: hello"),
        caller="operator", correlation_id="adaptive-resource-poll")))
    thread.start()
    assert started.wait(timeout=5)
    assert wakeup.wait(timeout=1)
    assert bridge.resource_reconciliation_interval_seconds() == 0.5
    finish.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert result["receipt"].status == "admitted_completed"
    assert bridge.resource_reconciliation_interval_seconds() == 5.0
    serving.close()


@pytest.mark.parametrize(("mode", "expected_status", "expected_calls"), [
    ("normal", "admitted_completed", 1),
    ("gaming", "deferred", 0),
])
def test_selected_gaming_profile_reaches_inference_governor_under_host_pressure(
        monkeypatch, tmp_path, mode, expected_status, expected_calls):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=95.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
        ]), clock=lambda: now.isoformat())
    bridge, serving, _, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner)
    bridge.set_workload_mode(mode)
    prompt = ("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
        "[SESSION_HISTORY_DATA]\nUSER_DATA: hello")
    correlation_id = "selected-profile-pressure-" + mode
    receipt = bridge.generate(prompt=prompt, caller="chat_service",
        correlation_id=correlation_id)

    assert receipt.status == expected_status
    assert model.calls == expected_calls
    linkage = receipt.request["linkage"]
    assert linkage["workload_mode"] == mode
    assert linkage["workload_evidence"]["configured_mode"] == mode
    assert linkage["host_resource_observation"]["pressure_labels"] == ["cpu_pressure"]
    lines = (tmp_path / "kernel-decisions.jsonl").read_text(
        encoding="utf-8").splitlines()
    decision = next(json.loads(line) for line in reversed(lines)
        if json.loads(line).get("action_kind") == "local_model_inference")
    delegated = decision["delegated_outcomes"]["runtime_governor"]
    assert delegated["evidence_refs"]["host_resource_evidence"]["report_id"] == (
        linkage["host_resource_observation"]["report_id"])
    assert delegated["evidence_refs"]["host_pressure_during_verified_game"] is False
    assert delegated["evidence_refs"]["gaming_workload_profile_host_pressure"] is (
        mode == "gaming")
    assert delegated["evidence_refs"]["gaming_workload_profile_evidence"]["mode"] == mode
    if mode == "gaming":
        assert delegated["reason"] == (
            "deferred_local_model_inference_under_host_pressure_in_gaming_mode")
    else:
        assert delegated["reason"] == "allowed"
    serving.close()


@pytest.mark.parametrize(("mode", "expected_status", "expected_calls"), [
    ("normal", "admitted_completed", 1),
    ("gaming", "deferred", 0),
])
def test_gaming_profile_defers_optional_inference_when_resource_telemetry_is_incomplete(
        monkeypatch, tmp_path, mode, expected_status, expected_calls):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    def missing_memory(*, observed_at=None):
        return HostCollectorResult("memory", "unavailable",
            observed_at or now.isoformat(), "synthetic_missing_memory",
            warnings=("sensor_unavailable",))

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                missing_memory),
        ]), clock=lambda: now.isoformat())
    bridge, serving, _, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner)
    bridge.set_workload_mode(mode)
    prompt = ("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
        "[SESSION_HISTORY_DATA]\nUSER_DATA: hello")
    receipt = bridge.generate(prompt=prompt, caller="chat_service",
        correlation_id="selected-profile-incomplete-" + mode)

    assert receipt.status == expected_status
    assert model.calls == expected_calls
    lines = (tmp_path / "kernel-decisions.jsonl").read_text(
        encoding="utf-8").splitlines()
    decision = next(json.loads(line) for line in reversed(lines)
        if json.loads(line).get("action_kind") == "local_model_inference")
    delegated = decision["delegated_outcomes"]["runtime_governor"]
    assert delegated["evidence_refs"][
        "gaming_workload_profile_resource_telemetry_incomplete"] is (mode == "gaming")
    assert delegated["evidence_refs"]["host_resource_evidence"]["status"] == "current"
    if mode == "gaming":
        assert delegated["reason"] == (
            "deferred_resource_telemetry_incomplete_in_gaming_mode")
    else:
        assert delegated["reason"] == "allowed"
    serving.close()


@pytest.mark.parametrize("missing_dimension", ["gpu_utilization", "vram_utilization"])
@pytest.mark.parametrize(("mode", "expected_status", "expected_calls"), [
    ("normal", "admitted_completed", 1),
    ("gaming", "deferred", 0),
])
def test_gaming_profile_requires_both_gpu_and_vram_samples_for_gpu_inference(
        monkeypatch, tmp_path, mode, expected_status, expected_calls,
        missing_dimension):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    gpu_values = {"gpu_utilization_percent": 42.0,
        "vram_utilization_percent": 38.0}
    gpu_values[missing_dimension + "_percent"] = None
    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
            HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
                collector("nvidia_gpu", devices=[gpu_values])),
        ]), clock=lambda: now.isoformat())
    bridge, serving, _, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        gpu_layers=24)
    monkeypatch.setattr(
        "sentientos.governed_local_model_invocation._verified_model_execution_profile",
        lambda *_: {
            "schema_version": "sentientos.model_execution_profile:v1",
            "engine": "llama_cpp", "accelerator_route": "gpu", "gpu_layers": 24,
            "configuration_digest": "a" * 64,
        })
    bridge.set_workload_mode(mode)
    prompt = ("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
        "[SESSION_HISTORY_DATA]\nUSER_DATA: hello")
    receipt = bridge.generate(prompt=prompt, caller="chat_service",
        correlation_id=f"partial-gpu-telemetry-{missing_dimension}-{mode}")

    assert receipt.status == expected_status
    assert model.calls == expected_calls
    host_observation = receipt.request["linkage"]["host_resource_observation"]
    assert host_observation["gpu_telemetry_available"] is True
    assert host_observation["gpu_telemetry_complete"] is False
    lines = (tmp_path / "kernel-decisions.jsonl").read_text(
        encoding="utf-8").splitlines()
    decision = next(json.loads(line) for line in reversed(lines)
        if json.loads(line).get("action_kind") == "local_model_inference")
    delegated = decision["delegated_outcomes"]["runtime_governor"]
    assert delegated["evidence_refs"]["host_resource_evidence"][
        "gpu_telemetry_complete"] is False
    if mode == "gaming":
        assert delegated["reason"] == (
            "deferred_resource_telemetry_incomplete_in_gaming_mode")
        assert delegated["evidence_refs"][
            "gaming_workload_profile_resource_telemetry_incomplete"] is True
    else:
        assert delegated["reason"] == "allowed"
    serving.close()


@pytest.mark.parametrize(("cpu_percent", "expected_status", "expected_closed"), [
    (95.0, "worker_closed", True),
    (20.0, "skipped", False),
])
def test_selected_gaming_profile_releases_optional_model_only_under_host_pressure(
        monkeypatch, tmp_path, cpu_percent, expected_status, expected_closed):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=cpu_percent)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
        ]), clock=lambda: now.isoformat())
    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        gpu_layers=24)
    bridge.set_workload_mode("gaming")

    result = bridge.reconcile_idle_game_resource_state()

    assert result["status"] == expected_status
    assert model.closed is expected_closed
    if expected_closed:
        assert serving.current_session() is None
        assert result["trigger_kind"] == "gaming_profile_resource_reconciliation"
        assert isinstance(result["release_receipt_id"], str)
        release_files = list((tmp_path / "state" / "installations" / "install-1" /
            "state" / "local-model" / "serving" /
            "resource-release-receipts").glob("*.json"))
        assert len(release_files) == 1
        receipt = json.loads(release_files[0].read_text(encoding="utf-8"))
        assert receipt["status"] == "worker_closed"
        assert receipt["inference_performed"] is False
        assert receipt["host_mutation_performed"] is False
        assert receipt["resource_observation"]["workload_mode"] == "gaming"
        assert receipt["resource_observation"]["workload_mode_source"] == "operator_selected"
        assert "game_workload_message_id" not in receipt["resource_observation"]
        decision = next(json.loads(line) for line in reversed(
            (tmp_path / "kernel-decisions.jsonl").read_text(
                encoding="utf-8").splitlines())
            if json.loads(line).get("action_kind") == "local_model_resource_release")
        delegated = decision["delegated_outcomes"]["runtime_governor"]
        assert delegated["allowed"] is True
        assert delegated["reason"] == "model_resource_release_fail_safe"
        evidence = delegated["evidence_refs"]["resource_observation_evidence"]
        assert evidence["status"] == "current"
        assert evidence["workload_mode"] == "gaming"
        assert evidence["workload_mode_source"] == "operator_selected"
        assert evidence["pressure_labels"] == ["cpu_pressure"]
        assert "game_workload_message_id" not in evidence
    else:
        assert result["reason"] == "current_host_pressure_evidence_required"
        assert serving.current_session() == session
        assert list((tmp_path / "state" / "installations" / "install-1" /
            "state" / "local-model" / "serving" /
            "resource-release-receipts").glob("*.json")) == []
        serving.close()


def test_idle_reconciliation_keeps_serving_session_without_verified_game(monkeypatch, tmp_path):
    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path)
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
    outcome = bridge.reconcile_idle_game_resource_state()
    assert outcome["status"] == "skipped"
    assert outcome["reason"] == "fresh_verified_game_evidence_required"
    assert model.calls == 0 and model.closed is False
    assert serving.current_session() == session
    serving.close()


def test_automatic_game_release_revalidates_game_after_host_collection(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "kernel-decisions.jsonl")

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=95.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
        ]), clock=lambda: now.isoformat())

    class GamePresenceChangesDuringCollection:
        calls = 0

        def observe(self, _names):
            self.calls += 1
            present = self.calls == 1
            return ForegroundGameObservation(
                "available", present,
                hashlib.sha256(b"examplegame.exe").hexdigest(), now.isoformat(),
                transport_provenance={"message_id": f"game-presence-{self.calls}"},
                game_process_running=present,
                running_process_name_digests=((hashlib.sha256(
                    b"examplegame.exe").hexdigest(),) if present else ()))

    detector = GamePresenceChangesDuringCollection()
    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, foreground_game_detector=detector,
        host_resource_observation_owner=host_owner, gpu_layers=0)
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])

    result = bridge.reconcile_idle_game_resource_state()

    assert result["status"] == "skipped", (result, detector.calls)
    assert result["reason"] == "fresh_verified_game_evidence_required"
    assert detector.calls == 2
    assert model.closed is False
    assert serving.current_session() == session
    assert list((tmp_path / "state" / "installations" / "install-1" /
        "state" / "local-model" / "serving" /
        "resource-release-receipts").glob("*.json")) == []
    serving.close()


@pytest.mark.parametrize("mode,style_expected", [("normal", False), ("gaming", True)])
def test_gaming_style_is_bound_into_the_exact_serving_prompt(monkeypatch, tmp_path, mode, style_expected):
    bridge, _, _, model, _, _ = setup(monkeypatch, tmp_path)
    bridge.set_workload_mode(mode)
    prompt = ("[SYSTEM_INSTRUCTION]\nBase rules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
              "[SESSION_HISTORY_DATA]\nUSER_DATA: hello")

    receipt = bridge.generate(prompt=prompt, caller="chat_service", correlation_id="gaming-style")

    observed_prompt = model.prompts[0]
    from sentientos.gaming_workload_policy import GamingWorkloadPolicy
    instruction = GamingWorkloadPolicy.GAMING_CHAT_STYLE_INSTRUCTION
    assert (instruction in observed_prompt) is style_expected
    assert receipt.request["linkage"].get("workload_response_style") == (
        GamingWorkloadPolicy.GAMING_CHAT_STYLE_ID if style_expected else None)
    assert receipt.request["linkage"].get("max_backend_threads") == (2 if style_expected else None)
    assert receipt.generation_config["actual_generation_parameters"].get(
        "max_backend_threads") == (2 if style_expected else None)




def test_screen_observation_style_is_preserved_by_exact_serving(monkeypatch, tmp_path):
    bridge, _, _, model, _, _ = setup(monkeypatch, tmp_path)
    bridge.set_workload_mode("gaming")
    prompt = (
        "[SYSTEM_INSTRUCTION]\nCompact screen rules."
        "\n[VERIFIED_RUNTIME_CONTEXT]\n{}"
        "\n[SESSION_HISTORY_DATA]"
        "\n[CURRENT_SCREEN_OBSERVATION_UNTRUSTED]\nSCREEN_DATA"
    )

    receipt = bridge.generate(
        prompt=prompt, caller="chat_service", correlation_id="screen-observation",
        caller_linkage={"chat_response_style": "screen_observation"},
    )

    observed_prompt = model.prompts[0]
    from sentientos.gaming_workload_policy import GamingWorkloadPolicy
    assert GamingWorkloadPolicy.GAMING_SCREEN_OBSERVATION_INSTRUCTION in observed_prompt
    assert GamingWorkloadPolicy.GAMING_CHAT_STYLE_INSTRUCTION not in observed_prompt
    assert receipt.request["linkage"]["caller_context"]["chat_response_style"] == (
        "screen_observation")

def test_gaming_workload_requests_ollama_unload_after_chat_turn():
    from sentientos.chat_service import DevelopmentLocalChatInference
    from sentientos.governed_local_model_invocation import LocalModelInvocationBudget

    class Invoker:
        model = SimpleNamespace(active_identity=SimpleNamespace(engine="ollama"))
        release_calls = 0

        def build_request(self, **kwargs):
            return kwargs

        def invoke(self, request):
            return request

        def release_model_residency(self):
            self.release_calls += 1
            return SimpleNamespace(status="released",
                to_dict=lambda: {"status": "released"})

    invoker = Invoker()
    inference = DevelopmentLocalChatInference(invoker)
    inference.set_workload_mode("gaming")
    assert invoker.release_calls == 1
    assert inference.current_workload_state()["residency_release"] == {
        "status": "released"}
    prompt = ("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
              "[SESSION_HISTORY_DATA]\nUSER_DATA: hello")
    request = inference.generate(prompt=prompt, caller="test",
        correlation_id="gaming-ollama", budget=LocalModelInvocationBudget(),
        caller_linkage={})

    assert request["linkage"]["workload_mode"] == "gaming"
    assert request["linkage"]["ollama_keep_alive"] == "0"


def test_bridge_foreground_observation_controls_governed_chat_budget_and_receipt_lineage(
        monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    stamp = now.isoformat()
    source_key = b"windows-foreground-test-key-material-32-bytes"
    core_key = b"sentientos-core-test-key-material-32-bytes"
    source_id, source_generation = "windows-foreground", "windows-observer-generation-1"
    runtime = CompanionBridgeLoopbackRuntime(
        receiver=CompanionBridgeReceiver(source_keys={source_id: source_key},
            expected_generations={source_id: source_generation}),
        acknowledgment_source_id="sentientos-core",
        acknowledgment_generation_id="core-generation-1",
        acknowledgment_key=core_key, queue_capacity=2)
    port = runtime.start()
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=source_id,
        generation_id=source_generation, max_observation_age_seconds=5)
    bridge, serving, _, model, _, _ = setup(
        monkeypatch, tmp_path, foreground_game_detector=detector)
    bridge.set_workload_mode("automatic", ("ExampleGame.exe",))
    client = CompanionBridgeLoopbackClient(port=port,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"sentientos-core": core_key},
            expected_generations={"sentientos-core": "core-generation-1"}),
        timeout_seconds=1.0)
    class WindowsObservation:
        def observe(self, _names):
            return ForegroundGameObservation(
                "available", True, hashlib.sha256(b"examplegame.exe").hexdigest(), stamp)

    publisher = WindowsForegroundBridgePublisher(
        detector=WindowsObservation(),
        client=client, source_id=source_id, session_id="observer-session-1",
        generation_id=source_generation, source_key=source_key)
    try:
        publisher.publish_once(("ExampleGame.exe",))
        prompt = ("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
              "[SESSION_HISTORY_DATA]\nUSER_DATA: hello")
        receipt = bridge.generate(prompt=prompt, caller="chat_service", correlation_id="bridged-game")

        assert receipt.status == "admitted_completed"
        assert receipt.generation_config["max_new_tokens"] <= 96
        from sentientos.gaming_workload_policy import GamingWorkloadPolicy
        assert GamingWorkloadPolicy.GAMING_CHAT_STYLE_INSTRUCTION in model.prompts[0]
        linkage = receipt.request["linkage"]
        assert linkage["workload_mode"] == "gaming"
        assert linkage["max_backend_threads"] == 2
        assert receipt.generation_config["actual_generation_parameters"][
            "max_backend_threads"] == 2
        assert model.generation_parameters[0]["max_backend_threads"] == 2
        state = bridge.current_workload_state()
        assert state["configured_game_process_names"] == ["examplegame.exe"]
        evidence = linkage["workload_evidence"]
        assert evidence["mode_source"] == "foreground_allowlist_match"
        assert evidence["transport_provenance"]["source_id"] == source_id
        assert evidence["transport_provenance"]["generation_id"] == source_generation
        assert evidence["transport_provenance"]["sequence"] == 1
        assert evidence["transport_provenance"]["message_id"]
    finally:
        detector.close()
        serving.close()


@pytest.mark.parametrize("trigger", ["deferred_inference", "idle_game_reconciliation",
    "idle_nominal_pressure", "idle_cpu_pressure", "deferred_cpu_pressure",
    "idle_game_gpu_residency", "deferred_thermal_pressure",
    "idle_game_frame_pressure", "idle_game_frame_pressure_mismatched_process",
    "idle_game_frame_pressure_active_inference",
    "idle_game_frame_pressure_active_inference_unconfirmed",
    "idle_game_frame_pressure_active_inference_scheduler"])
def test_verified_game_resource_governance_defers_or_releases_before_effect(
        monkeypatch, tmp_path, trigger):
    now = datetime.now(timezone.utc)
    source_id, generation_id = "windows-edge", "windows-edge-generation-1"
    source_key = b"windows-game-pressure-source-key-32"
    verifier = CompanionBridgeReceiver(source_keys={source_id: source_key},
        expected_generations={source_id: generation_id})
    accepted = []
    frame_observations = 0

    def observe_frames(_pid):
        nonlocal frame_observations
        frame_observations += 1
        if trigger in {"idle_game_frame_pressure_active_inference",
                "idle_game_frame_pressure_active_inference_unconfirmed",
                "idle_game_frame_pressure_active_inference_scheduler"}:
            return (((16.7, 52.0), "f" * 64)
                if frame_observations >= 2 else ((), None))
        if trigger in {"idle_game_frame_pressure",
                "idle_game_frame_pressure_mismatched_process"}:
            return ((16.7, 52.0), "f" * 64)
        return (), None

    observer = WindowsGamePerformanceObserver(
        system_provider=lambda: "Windows",
        process_provider=lambda _pid: {"name": "examplegame.exe",
            "cpu_percent": 12.0, "rss_bytes": 4096},
        frame_provider=observe_frames,
        clock=lambda: now.isoformat())
    client = CompanionBridgeLoopbackClient(port=1,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core": b"core-game-ack-key-material-32-bytes"},
            expected_generations={"wsl-core": "wsl-core-generation-1"}))

    def accept_sample(encoded):
        message = verifier.accept(encoded)
        accepted.append(message)
        return message

    client.send = accept_sample
    publisher = WindowsGamePerformanceBridgePublisher(observer=observer,
        client=client, source_id=source_id, session_id="game-pressure-test",
        generation_id=generation_id, source_key=source_key, process_id=733)
    publisher.publish_once()

    class OneMessageReceiver:
        def __init__(self, index=0):
            self.index = index

        def receive(self, timeout=None):
            del timeout
            message = accepted[self.index]
            self.index += 1
            return message

    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    game_evidence = GamePerformanceBridgeDetector(receiver=OneMessageReceiver(),
        source_id=source_id, generation_provider=lambda: generation_id,
        clock=lambda: now).receive_once()
    assert kernel.observe_verified_game_performance(game_evidence)
    game_workload_digest = hashlib.sha256(("othergame.exe"
        if trigger == "idle_game_frame_pressure_mismatched_process"
        else "examplegame.exe").encode("utf-8")).hexdigest()
    game_workload = ForegroundGameObservation("available", True, game_workload_digest,
        now.isoformat(), transport_provenance={"message_id": "e" * 64,
            "source_id": "windows-foreground", "session_id": "foreground-session",
            "generation_id": "foreground-generation-1", "sequence": 1,
            "envelope_created_at": now.isoformat()})
    assert kernel.observe_verified_game_workload(game_workload)

    class VerifiedGameDetector:
        def observe(self, process_names):
            del process_names
            return game_workload

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)
    gpu_metrics = ({"gpu": 22.0, "vram": 47.0}
        if trigger in {"idle_nominal_pressure", "idle_cpu_pressure", "deferred_cpu_pressure",
            "idle_game_gpu_residency", "deferred_thermal_pressure",
            "idle_game_frame_pressure", "idle_game_frame_pressure_mismatched_process",
            "idle_game_frame_pressure_active_inference",
            "idle_game_frame_pressure_active_inference_unconfirmed",
            "idle_game_frame_pressure_active_inference_scheduler"}
        else {"gpu": 94.0, "vram": 91.0})
    cpu_utilization = 95.0 if trigger in {
        "idle_cpu_pressure", "deferred_cpu_pressure"} else 20.0

    def collect_gpu(*, observed_at=None):
        return HostCollectorResult("nvidia_gpu", "available",
            observed_at or now.isoformat(), "synthetic_test_fixture",
            values={"device_count": 1, "devices": [{"index": 0,
                "gpu_utilization_percent": gpu_metrics["gpu"],
                "vram_utilization_percent": gpu_metrics["vram"]}]})

    def collect_thermal(*, observed_at=None):
        return HostCollectorResult("thermal_sensors", "available",
            observed_at or now.isoformat(), "synthetic_test_fixture",
            values={"zones": [{"id": "cpu", "temperature_c":
                92.0 if trigger == "deferred_thermal_pressure" else 55.0,
                "telemetry_only": True, "control_available": False}]})

    host_plan = build_observation_plan(specs=[
        HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
            collector("cpu", utilization_percent=cpu_utilization)),
        HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
            collector("memory", used_percent=40.0)),
        HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
            collect_gpu),
        HostObservationCollectorSpec("thermal_sensors", False, ("linux", "unknown"), 4,
            collect_thermal)
    ])
    host_resource_owner = HostResourceRuntimeCoordinator(
        kernel=kernel, runtime_state_root=tmp_path / "host-resource",
        plan=host_plan, clock=lambda: now.isoformat())
    active_started = threading.Event()
    active_cancelled = threading.Event()
    finish_generation = threading.Event()

    def active_generation():
        active_started.set()
        if trigger == "idle_game_frame_pressure_active_inference_unconfirmed":
            if not finish_generation.wait(timeout=5):
                raise AssertionError("fixture inference finish timed out")
            return "answer"
        if not active_cancelled.wait(timeout=5):
            raise AssertionError("game-pressure cancellation was not delivered")
        raise RuntimeError("fixture_generation_cancelled_for_game_priority")

    bridge, serving, _, model, _, _ = setup(
        monkeypatch, tmp_path, kernel_override=kernel,
        host_resource_observation_owner=host_resource_owner,
        foreground_game_detector=VerifiedGameDetector(),
        gpu_layers=24 if trigger == "idle_game_gpu_residency" else 0,
        on_generate=active_generation
            if trigger in {"idle_game_frame_pressure_active_inference",
                "idle_game_frame_pressure_active_inference_unconfirmed",
                "idle_game_frame_pressure_active_inference_scheduler"} else None)
    if trigger in {"idle_game_frame_pressure_active_inference",
            "idle_game_frame_pressure_active_inference_scheduler"}:
        model.cancel_pending_generation = lambda: (active_cancelled.set() or True)
    elif trigger == "idle_game_frame_pressure_active_inference_unconfirmed":
        model.cancel_pending_generation = lambda: False
    original_close = model.close

    def simulated_release() -> None:
        original_close()
        gpu_metrics.update(gpu=12.0 if trigger in {
            "idle_game_frame_pressure", "idle_game_frame_pressure_active_inference",
            "idle_game_frame_pressure_active_inference_scheduler"}
            else 22.0,
            vram=40.0 if trigger in {
                "idle_game_frame_pressure", "idle_game_frame_pressure_active_inference",
                "idle_game_frame_pressure_active_inference_scheduler"}
                else 47.0)

    model.close = simulated_release
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])

    if trigger in {"deferred_inference", "deferred_cpu_pressure", "deferred_thermal_pressure"}:
        gaming_prompt = ("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
            "[SESSION_HISTORY_DATA]\nUSER_DATA: hello")
        receipt = bridge.generate(prompt=gaming_prompt, caller="chat_service",
            correlation_id="verified-game-resource-pressure")
        assert receipt.status == "deferred"
        host_reference = receipt.request["linkage"]["host_resource_observation"]
        assert host_reference["observation_correlation_id"] == (
            "local-chat-inference-" + hashlib.sha256(
                b"verified-game-resource-pressure").hexdigest()[:32])
        assert host_reference["status"] == "current"
        assert host_reference["no_effect_authority"] is True
        expected_pressure = {"deferred_cpu_pressure": ["cpu_pressure"],
            "deferred_thermal_pressure": ["thermal_pressure"],
            "deferred_inference": ["gpu_pressure"]}[trigger]
        assert host_reference["pressure_labels"] == expected_pressure
    elif trigger in {"idle_game_frame_pressure_active_inference",
            "idle_game_frame_pressure_active_inference_unconfirmed",
            "idle_game_frame_pressure_active_inference_scheduler"}:
        invocation_results = {}
        inference = bridge
        resource_custody = None
        resource_ledger = None
        resource_allocation_id = None
        if trigger == "idle_game_frame_pressure_active_inference_scheduler":
            from sentientos.governed_local_model_invocation import LocalModelInvocationBudget
            from sentientos.governed_local_model_resource_allocation import (
                GovernedLocalModelResourceBounds,
                GovernedLocalModelResourcePolicy,
            )
            from sentientos.production_chat_resource_context import (
                ResourceBackedProductionChatInference,
            )
            from sentientos.production_chat_resource_provisioning import (
                load_production_chat_resource_context_owner,
            )
            from sentientos.production_chat_resource_provisioning_bundle_producer import (
                produce_production_chat_resource_provisioning_bundle,
            )
            from tests.test_production_chat_resource_provisioning_bundle_producer import (
                encoded, inputs as provisioning_inputs,
            )

            installation, provisioning_artifacts = provisioning_inputs(
                tmp_path / "scheduled-resource-provisioning", calls=2)
            resource_bounds = GovernedLocalModelResourceBounds(8000, 4000, 512, 30.0, 2)
            resource_policy = GovernedLocalModelResourcePolicy.create(
                epoch=1, max_resource_specific_bounds=resource_bounds,
                not_before="2026-09-21T08:00:00Z",
                valid_until="2026-09-21T09:15:00Z")
            provisioning_artifacts["requested_bounds"] = resource_bounds
            provisioning_artifacts["resource_policy_artifact"] = encoded(
                resource_policy.to_dict())
            bundle = produce_production_chat_resource_provisioning_bundle(
                installation, "scheduled-chat", **provisioning_artifacts)
            resource_custody = load_production_chat_resource_context_owner(
                installation, "scheduled-chat",
                clock=lambda: "2026-09-21T08:30:00Z",
                nonce_source=iter(("scheduled-attempt-one", "scheduled-attempt-two")).__next__)
            resource_allocation_id = bundle.allocation_id
            resource_ledger = resource_custody.allocator.ledger
            inference = ResourceBackedProductionChatInference(bridge, resource_custody)
        active_prompt = ("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
            "[SESSION_HISTORY_DATA]\nUSER_DATA: optional inference")

        def invoke_while_game_is_running():
            arguments = {"prompt": active_prompt, "caller": "chat_service",
                "correlation_id": "frame-pressure-active-inference"}
            if resource_custody is not None:
                arguments["budget"] = LocalModelInvocationBudget(8000, 4000, 512, 30.0, 2)
                arguments["caller_linkage"] = {}
            invocation_results["receipt"] = inference.generate(**arguments)

        invocation_thread = threading.Thread(target=invoke_while_game_is_running)
        if trigger != "idle_game_frame_pressure_active_inference_scheduler":
            invocation_thread.start()
            assert active_started.wait(timeout=5)
            publisher.publish_once()
            changed_game_evidence = GamePerformanceBridgeDetector(
                receiver=OneMessageReceiver(index=1), source_id=source_id,
                generation_provider=lambda: generation_id, clock=lambda: now
            ).receive_once()
            assert kernel.observe_verified_game_performance(changed_game_evidence)

        scheduler_state = None
        if trigger == "idle_game_frame_pressure_active_inference_scheduler":
            import asyncio
            from types import SimpleNamespace
            from sentientos import chat_service

            service = SimpleNamespace(
                reconcile_workload_state=inference.reconcile_workload_state,
                resource_reconciliation_interval_seconds=(
                    inference.resource_reconciliation_interval_seconds),
                set_resource_reconciliation_wakeup=(
                    inference.set_resource_reconciliation_wakeup),
                close_outputs=lambda: None)
            previous_composition = chat_service._PRODUCTION_COMPOSITION
            previous_reconciliation_task = chat_service._RESOURCE_RECONCILIATION_TASK
            chat_service._PRODUCTION_COMPOSITION = chat_service.ProductionChatComposition(
                service, serving)
            chat_service._RESOURCE_RECONCILIATION_TASK = None

            async def run_reconciliation_scheduler():
                await chat_service._startup_event()
                try:
                    invocation_thread.start()
                    if not await asyncio.to_thread(active_started.wait, 5):
                        raise AssertionError("active inference did not start")
                    publisher.publish_once()
                    changed = GamePerformanceBridgeDetector(
                        receiver=OneMessageReceiver(index=1), source_id=source_id,
                        generation_provider=lambda: generation_id, clock=lambda: now
                    ).receive_once()
                    assert kernel.observe_verified_game_performance(changed)
                    if not await asyncio.to_thread(active_cancelled.wait, 5):
                        raise AssertionError("scheduler did not deliver game-priority cancellation")
                    await asyncio.to_thread(invocation_thread.join, 5)
                    assert not invocation_thread.is_alive()
                    return chat_service._RESOURCE_RECONCILIATION_TASK is not None
                finally:
                    await chat_service._shutdown_event()

            try:
                scheduler_state = asyncio.run(run_reconciliation_scheduler())
            finally:
                chat_service._PRODUCTION_COMPOSITION = previous_composition
                chat_service._RESOURCE_RECONCILIATION_TASK = previous_reconciliation_task
                if resource_custody is not None:
                    resource_custody.close()
            if resource_ledger is not None and resource_allocation_id is not None:
                assert resource_ledger.remaining_calls(resource_allocation_id) == 1
                assert len(resource_ledger._state["attempts"]) == 1
                assert resource_ledger._state["receipts"][-1][
                    "effect_receipt_digest"] == invocation_results["receipt"].receipt_digest
            reconciliation = {"status": "worker_closed",
                "trigger_kind": "idle_game_frame_pressure_reconciliation",
                "active_inference_cancellation_confirmed": True}
        else:
            reconciliation = bridge.reconcile_idle_game_resource_state()
        assert reconciliation["trigger_kind"] == (
            "idle_game_frame_pressure_reconciliation")
        if trigger in {"idle_game_frame_pressure_active_inference",
                "idle_game_frame_pressure_active_inference_scheduler"}:
            invocation_thread.join(timeout=5)
            assert not invocation_thread.is_alive()
            assert reconciliation["status"] == "worker_closed"
            assert reconciliation["active_inference_cancellation_confirmed"] is True
            assert invocation_results["receipt"].status == "cancelled"
            assert invocation_results["receipt"].output_text is None
            assert model.closed is True
            assert serving.current_session() is None
            if trigger == "idle_game_frame_pressure_active_inference_scheduler":
                assert scheduler_state is True
        else:
            assert reconciliation["status"] == "release_effect_unconfirmed"
            assert reconciliation["active_inference_cancellation_confirmed"] is False
            duplicate = bridge.reconcile_idle_game_resource_state()
            assert duplicate == {"status": "skipped",
                "reason": "game_pressure_release_already_attempted_for_observation"}
            publisher.publish_once()
            newer_game_evidence = GamePerformanceBridgeDetector(
                receiver=OneMessageReceiver(index=2), source_id=source_id,
                generation_provider=lambda: generation_id, clock=lambda: now
            ).receive_once()
            assert kernel.observe_verified_game_performance(newer_game_evidence)
            retry = bridge.reconcile_idle_game_resource_state()
            assert retry["status"] == "release_effect_unconfirmed"
            assert retry["active_inference_cancellation_confirmed"] is False
            finish_generation.set()
            invocation_thread.join(timeout=5)
            assert not invocation_thread.is_alive()
            assert invocation_results["receipt"].status == "admitted_completed"
            assert model.closed is False
            assert serving.current_session() is not None
    else:
        if trigger in {"idle_game_frame_pressure",
                "idle_game_frame_pressure_mismatched_process"}:
            nominal = host_resource_owner.run_cycle(
                correlation_id="frame-pressure-test-nominal-host-sample")
            assert nominal is not None
            assert nominal.pressure_report.pressure_labels == ("nominal",)
        reconciliation = bridge.reconcile_idle_game_resource_state()
        if trigger == "idle_game_gpu_residency":
            assert reconciliation["status"] == "worker_closed"
            assert reconciliation["trigger_kind"] == "idle_game_gpu_residency"
            assert model.closed is True
            assert serving.current_session() is None
            assert isinstance(reconciliation["release_receipt_id"], str)
        elif trigger == "idle_game_frame_pressure_mismatched_process":
            assert reconciliation["status"] == "denied"
            assert reconciliation["trigger_kind"] == (
                "idle_game_frame_pressure_reconciliation")
            assert model.closed is False
            assert serving.current_session() is not None
        elif trigger == "idle_game_frame_pressure":
            assert reconciliation["status"] == "worker_closed"
            assert reconciliation["trigger_kind"] == (
                "idle_game_frame_pressure_reconciliation")
            assert model.closed is True
            assert serving.current_session() is None
            assert isinstance(reconciliation["release_receipt_id"], str)
        elif trigger == "idle_nominal_pressure":
            assert reconciliation["status"] == "skipped"
            assert reconciliation["reason"] == "current_host_pressure_evidence_required"
            assert model.closed is False
            assert serving.current_session() is not None
            serving.close()
            return
        if trigger not in {"idle_game_gpu_residency", "idle_game_frame_pressure",
                "idle_game_frame_pressure_mismatched_process"}:
            assert reconciliation["status"] == "worker_closed"
            assert isinstance(reconciliation["release_receipt_id"], str)
            assert reconciliation["trigger_kind"] == "idle_game_reconciliation"
            assert reconciliation["observation_correlation_id"].startswith(
                "local-chat-reconciliation-")

    assert model.calls == (1 if trigger in {
        "idle_game_frame_pressure_active_inference",
        "idle_game_frame_pressure_active_inference_scheduler",
        "idle_game_frame_pressure_active_inference_unconfirmed"} else 0)
    if trigger in {"deferred_inference", "deferred_cpu_pressure", "deferred_thermal_pressure"}:
        decisions = [json.loads(line) for line in (tmp_path / "kernel-decisions.jsonl").read_text(
            encoding="utf-8").splitlines()]
        decision = next(item for item in decisions
            if item.get("action_kind") == "local_model_inference")
        delegated = decision["delegated_outcomes"]["runtime_governor"]
        assert delegated["reason"] == (
            "deferred_local_model_inference_under_host_pressure_during_game")
        assert delegated["evidence_refs"]["game_performance_evidence"]["message_id"] == (
            accepted[0].message_id)
        assert delegated["evidence_refs"]["host_resource_evidence"]["report_id"] == (
            receipt.request["linkage"]["host_resource_observation"]["report_id"])
    expected_collector_count = (12
        if trigger == "idle_game_frame_pressure_active_inference_scheduler" else
        4 if trigger in {"idle_game_gpu_residency",
            "idle_game_frame_pressure_mismatched_process",
            "idle_game_frame_pressure_active_inference_unconfirmed"} else 8)
    assert host_resource_owner.collector_call_count == expected_collector_count
    release_receipts = list((tmp_path / "state" / "installations" / "install-1" /
        "state" / "local-model" / "serving" /
        "resource-release-receipts").glob("*.json"))
    expected_release_receipt_count = (2
        if trigger == "idle_game_frame_pressure_active_inference_unconfirmed" else 1)
    assert len(release_receipts) == expected_release_receipt_count
    decoded_releases = [json.loads(path.read_text(encoding="utf-8"))
        for path in release_receipts]
    if trigger == "idle_game_frame_pressure_active_inference_unconfirmed":
        assert model.closed is False
        assert serving.current_session() is not None
        assert all(release["status"] == "release_effect_unconfirmed"
            for release in decoded_releases)
        assert all(release["active_inference_preemption_requested"] is True
            for release in decoded_releases)
        assert all(release["active_inference_cancellation_confirmed"] is False
            for release in decoded_releases)
        assert all(release["close_failure"] ==
            "active_inference_cancellation_unconfirmed" for release in decoded_releases)
        assert {release["resource_observation"]["game_performance_message_id"]
            for release in decoded_releases} == {accepted[1].message_id, accepted[2].message_id}
        serving.close()
        return
    release = decoded_releases[0]
    if trigger == "idle_game_frame_pressure_mismatched_process":
        assert model.closed is False
        assert serving.current_session() is not None
        assert release["status"] == "denied"
        assert release["resource_observation"]["game_performance_process_name_digest"] == (
            hashlib.sha256(b"examplegame.exe").hexdigest())
        serving.close()
        return
    assert model.closed is True
    assert serving.current_session() is None
    assert release["status"] == "worker_closed"
    if trigger == "idle_game_gpu_residency":
        assert release["trigger_kind"] == "idle_game_gpu_residency"
        assert release["resource_observation"]["game_workload_message_id"] == "e" * 64
        assert release["resource_observation"]["model_gpu_layers"] == 24
        assert release["resource_observation"]["host_telemetry_used_for_admission"] is False
        comparison = release["resource_measurement_comparison"]
        assert comparison["before"] is None
        assert comparison["before_sample_kind"] == "unavailable"
        assert comparison["after"]["gpu_utilization_percent"] == 22.0
        assert comparison["after"]["vram_utilization_percent"] == 47.0
        assert comparison["gpu_utilization_delta_percentage_points"] is None
        assert comparison["vram_utilization_delta_percentage_points"] is None
        assert comparison["interpretation"] == (
            "sample_delta_only; telemetry_does_not_establish_causation")
        assert release["inference_performed"] is False
        assert release["host_mutation_performed"] is False
        serving.close()
        return
    if trigger in {"idle_game_frame_pressure",
            "idle_game_frame_pressure_active_inference",
            "idle_game_frame_pressure_active_inference_scheduler"}:
        expected_game_performance_message_id = (
            accepted[1].message_id
                if trigger in {"idle_game_frame_pressure_active_inference",
                    "idle_game_frame_pressure_active_inference_scheduler"}
            else accepted[0].message_id)
        assert release["trigger_kind"] == "idle_game_frame_pressure_reconciliation"
        assert release["resource_observation"]["game_performance_message_id"] == (
            expected_game_performance_message_id)
        assert release["resource_observation"]["game_performance_process_id_digest"] == (
            game_evidence.process_id_digest)
        assert release["resource_observation"]["game_performance_process_name_digest"] == (
            game_evidence.process_name_digest)
        assert release["resource_observation"]["frame_time_p95_ms"] == 52.0
        assert release["resource_observation"]["hitch_count_over_50ms"] == 1
        assert release["active_inference_preemption_requested"] is (
            trigger in {"idle_game_frame_pressure_active_inference",
                "idle_game_frame_pressure_active_inference_scheduler"})
        assert release["active_inference_cancellation_confirmed"] is (
            True if trigger in {"idle_game_frame_pressure_active_inference",
                "idle_game_frame_pressure_active_inference_scheduler"} else None)
        assert "host_report_id" not in release["resource_observation"]
        postflight = release["post_release_observation"]
        assert postflight["status"] == "current"
        assert postflight["no_effect_authority"] is True
        assert postflight["gpu_utilization_percent"] == 12.0
        assert postflight["vram_utilization_percent"] == 40.0
        beforeflight = release["before_release_observation"]
        assert beforeflight["status"] == "current"
        assert beforeflight["no_effect_authority"] is True
        assert beforeflight["gpu_utilization_percent"] == 22.0
        assert beforeflight["vram_utilization_percent"] == 47.0
        comparison = release["resource_measurement_comparison"]
        assert comparison["status"] == "comparable"
        assert comparison["before_sample_kind"] == "recent_cached_observation"
        assert comparison["gpu_utilization_delta_percentage_points"] == -10.0
        assert comparison["vram_utilization_delta_percentage_points"] == -7.0
        assert comparison["interpretation"] == (
            "sample_delta_only; telemetry_does_not_establish_causation")
        assert release["post_release_measurement_interpretation"] == (
            "read_only_sample_after_worker_close; pre-release sample is a "
            "recent cache entry when available; "
            "telemetry_does_not_establish_causation")
        assert release["inference_performed"] is False
        assert release["host_mutation_performed"] is False
        serving.close()
        return
    assert release["trigger_kind"] == (
        "deferred_inference" if trigger in {"deferred_inference", "deferred_cpu_pressure",
            "deferred_thermal_pressure"}
        else "idle_game_reconciliation")
    assert release["resource_observation"]["game_workload_message_id"] == "e" * 64
    expected_release_pressure = {"idle_cpu_pressure": ["cpu_pressure"],
        "deferred_cpu_pressure": ["cpu_pressure"],
        "deferred_thermal_pressure": ["thermal_pressure"]}
    assert release["resource_observation"]["pressure_labels"] == (
        expected_release_pressure.get(trigger, ["gpu_pressure"]))
    comparison = release["resource_measurement_comparison"]
    assert comparison["status"] == "comparable"
    assert comparison["before"]["gpu_telemetry_sources"] == [{
        "collector_id": "nvidia_gpu", "status": "available",
        "source": "synthetic_test_fixture"}]
    expected_delta = (0.0 if trigger in {"idle_cpu_pressure", "deferred_cpu_pressure",
            "deferred_thermal_pressure"}
        else -72.0)
    expected_vram_delta = (0.0 if trigger in {"idle_cpu_pressure", "deferred_cpu_pressure",
            "deferred_thermal_pressure"}
        else -44.0)
    assert comparison["gpu_utilization_delta_percentage_points"] == expected_delta
    assert comparison["vram_utilization_delta_percentage_points"] == expected_vram_delta
    assert comparison["interpretation"] == (
        "sample_delta_only; telemetry_does_not_establish_causation")
    assert release["worker_exit_observed"] is None
    assert release["inference_performed"] is False
    assert release["host_mutation_performed"] is False
    serving.close()


def test_inference_admission_uses_its_own_observation_when_another_is_newer(
        monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    gpu_percent = {"value": 94.0}

    def collect(collector_id, values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values())

    plan = build_observation_plan(specs=[
        HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
            collect("cpu", lambda: {"utilization_percent": 20.0})),
        HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
            collect("memory", lambda: {"used_percent": 40.0})),
        HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
            collect("nvidia_gpu", lambda: {"device_count": 1, "devices": [{
                "index": 0, "gpu_utilization_percent": gpu_percent["value"],
                "vram_utilization_percent": gpu_percent["value"]}]})),
    ])
    owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource", plan=plan,
        clock=lambda: now.isoformat())
    inference_correlation = "inference-owned-sample"
    observation_id = "local-chat-inference-" + hashlib.sha256(
        inference_correlation.encode("utf-8")).hexdigest()[:32]
    pressured = owner.run_cycle(correlation_id=observation_id)
    assert pressured is not None
    gpu_percent["value"] = 20.0
    newer_nominal = owner.run_cycle(correlation_id="local-chat-inference-newer-nominal")
    assert newer_nominal is not None
    assert governor._host_resource_evidence["report_id"] == newer_nominal.pressure_report.report_id

    game_observation = ForegroundGameObservation("available", True, "a" * 64,
        now.isoformat(), transport_provenance={"message_id": "b" * 64,
            "source_id": "windows-edge", "session_id": "game-session",
            "generation_id": "edge-generation", "sequence": 1,
            "envelope_created_at": now.isoformat()})
    assert kernel.observe_verified_game_workload(game_observation)
    decision = governor.admit_action("local_model_inference", "chat_service",
        inference_correlation, metadata={"purpose": "local_user_chat",
            "host_resource_observation_id": observation_id})

    assert decision.allowed is False
    assert decision.reason == "deferred_local_model_inference_under_host_pressure_during_game"
    assert decision.evidence_refs["host_resource_evidence"]["report_id"] == (
        pressured.pressure_report.report_id)
    assert decision.evidence_refs["host_resource_evidence"][
        "observation_correlation_id"] == observation_id


def test_verified_game_presence_without_frame_metrics_prioritizes_game_when_resources_incomplete(
        monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    source_id, generation_id = "windows-foreground", "windows-foreground-generation-1"
    source_key = b"windows-foreground-priority-key-32-bytes"
    core_key = b"sentientos-core-priority-key-32-bytes"
    runtime = CompanionBridgeLoopbackRuntime(
        receiver=CompanionBridgeReceiver(source_keys={source_id: source_key},
            expected_generations={source_id: generation_id}),
        acknowledgment_source_id="sentientos-core",
        acknowledgment_generation_id="core-generation-1",
        acknowledgment_key=core_key, queue_capacity=2)
    port = runtime.start()
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=source_id,
        generation_id=generation_id, max_observation_age_seconds=5,
        clock=lambda: now)
    client = CompanionBridgeLoopbackClient(port=port,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"sentientos-core": core_key},
            expected_generations={"sentientos-core": "core-generation-1"}),
        timeout_seconds=1.0)

    class GameIsForeground:
        def observe(self, _names):
            return ForegroundGameObservation(
                "available", True, hashlib.sha256(b"examplegame.exe").hexdigest(),
                now.isoformat())

    publisher = WindowsForegroundBridgePublisher(detector=GameIsForeground(),
        client=client, source_id=source_id, session_id="active-game-session",
        generation_id=generation_id, source_key=source_key)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    governor = RuntimeGovernor()
    kernel = ControlPlaneKernel(runtime_governor=governor,
        decisions_path=tmp_path / "kernel-decisions.jsonl")

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_plan = build_observation_plan(specs=[
        HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
            collector("cpu", utilization_percent=20.0)),
        HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
            lambda *, observed_at=None: HostCollectorResult(
                "memory", "unavailable", observed_at or now.isoformat(),
                "synthetic_test_fixture", values={})),
        HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
            lambda *, observed_at=None: HostCollectorResult(
                "nvidia_gpu", "unavailable", observed_at or now.isoformat(),
                "synthetic_test_fixture", values={}))
    ])
    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource", plan=host_plan,
        clock=lambda: now.isoformat())
    bridge, serving, _, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, foreground_game_detector=detector,
        host_resource_observation_owner=host_owner)
    detector.set_game_workload_admission_owner(kernel)
    bridge.set_workload_mode("automatic", ("ExampleGame.exe",))
    try:
        publisher.publish_once(("ExampleGame.exe",))
        prompt = ("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
            "[SESSION_HISTORY_DATA]\nUSER_DATA: hello")
        receipt = bridge.generate(prompt=prompt, caller="chat_service",
            correlation_id="foreground-game-host-pressure")

        assert receipt.status == "deferred"
        assert model.calls == 0
        assert receipt.effects["local_model_inference"] is False
        decision = json.loads((tmp_path / "kernel-decisions.jsonl").read_text(
            encoding="utf-8").splitlines()[-1])
        delegated = decision["delegated_outcomes"]["runtime_governor"]
        assert delegated["reason"] == (
            "deferred_resource_telemetry_incomplete_during_game")
        game_ref = delegated["evidence_refs"]["game_workload_evidence"]
        assert game_ref["game_active"] is True
        assert game_ref["message_id"]
        assert delegated["evidence_refs"]["game_performance_evidence"][
            "status"] == "unavailable"
        host_ref = receipt.request["linkage"]["host_resource_observation"]
        assert host_ref["no_effect_authority"] is True
        assert host_ref["gpu_telemetry_available"] is False
        assert host_ref["status"] == "current"
        assert serving.current_session() is not None
    finally:
        detector.close()
        serving.close()


def test_serving_authority_reconstructs_commissioned_resource_profile(tmp_path):
    artifact = tmp_path / "model.gguf"
    artifact.write_bytes(b"profile-bound-model")
    profile = {"schema_version": LLAMA_CPP_RESOURCE_PROFILE_SCHEMA,
        "profile_id": "cpu-gaming-v1", "n_ctx": 512, "n_gpu_layers": 0,
        "n_threads": 4, "n_threads_batch": 2, "n_batch": 128, "n_ubatch": 64}
    load = {"engine": "llama_cpp", "n_ctx": 512, "n_gpu_layers": 0,
        "resource_profile": profile,
        "resource_profile_digest": llama_cpp_resource_profile_digest(profile)}
    options = {"gpu_layers": 0, "resource_profile_digest": load["resource_profile_digest"],
        "n_threads": 4, "n_threads_batch": 2, "n_batch": 128, "n_ubatch": 64}
    config = ModelConfig([ModelCandidate(artifact, "llama_cpp", "profile-model", options)],
        default_engine="llama_cpp", max_context_tokens=512,
        generation=GenerationConfig(max_new_tokens=8, temperature=0, top_p=1))
    expected = build_local_model_authority_map(config, allowed_roots=[tmp_path],
        observed_at="1970-01-01T00:00:00+00:00")
    session = SimpleNamespace(binding={"artifact_path": str(artifact),
        "model_id": "profile-model", "load_configuration": load,
        "authority_map_digest": expected.map_digest})

    actual = ProductionServingInferenceController._authority(session)

    assert actual.map_digest == expected.map_digest


def test_serving_authority_rejects_profile_digest_mismatch(tmp_path):
    artifact = tmp_path / "model.gguf"
    artifact.write_bytes(b"profile-bound-model")
    profile = {"schema_version": LLAMA_CPP_RESOURCE_PROFILE_SCHEMA,
        "profile_id": "cpu-gaming-v1", "n_ctx": 512, "n_gpu_layers": 0,
        "n_threads": 4, "n_threads_batch": 2, "n_batch": 128, "n_ubatch": 64}
    session = SimpleNamespace(binding={"artifact_path": str(artifact),
        "model_id": "profile-model", "load_configuration": {
            "engine": "llama_cpp", "n_ctx": 512, "n_gpu_layers": 0,
            "resource_profile": profile, "resource_profile_digest": "0" * 64},
        "authority_map_digest": "unused"})

    with pytest.raises(ProductionServingInferenceError, match="resource_profile_mismatch"):
        ProductionServingInferenceController._authority(session)


@pytest.mark.parametrize("outcome", [AdmissionOutcome.DENY, AdmissionOutcome.DEFER, AdmissionOutcome.QUARANTINE])
def test_inference_denial_occurs_before_generation(monkeypatch, tmp_path, outcome):
    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path, inference=outcome)
    receipt = bridge.generate(prompt="hello", caller="operator", correlation_id="denied-1")
    assert model.calls == 0 and receipt.effects["local_model_inference"] is False
    assert serving.current_session() == session


def test_pre_effect_stale_session_denies_generation(monkeypatch, tmp_path):
    bridge, serving, _, model, kernel, current = setup(monkeypatch, tmp_path)
    original = kernel.admit
    def admit(request):
        decision = original(request)
        if request.authority_class is AuthorityClass.LOCAL_MODEL_INFERENCE:
            current[0] = {**current[0], "active_state": {**current[0]["active_state"], "generation": 2}}
        return decision
    kernel.admit = admit
    receipt = bridge.generate(prompt="hello", caller="operator", correlation_id="stale-before")
    assert model.calls == 0 and receipt.status == "backend_failure" and serving.current_session() is None


def test_post_generation_stale_output_is_suppressed_and_effect_recorded(monkeypatch, tmp_path):
    holder = {}
    def change():
        evidence = holder["current"][0]
        holder["current"][0] = {**evidence, "active_state": {**evidence["active_state"], "generation": 2}}
    bridge, serving, _, model, _, current = setup(monkeypatch, tmp_path, on_generate=change); holder["current"] = current
    receipt = bridge.generate(prompt="hello", caller="operator", correlation_id="stale-after")
    assert model.calls == 1 and receipt.output_text is None
    assert receipt.effects["local_model_inference"] is True and receipt.output_digest is not None
    assert serving.current_session() is None


def test_requires_current_session_and_exposes_no_generation_escape(monkeypatch, tmp_path):
    bridge, serving, session, _, _, _ = setup(monkeypatch, tmp_path)
    assert not any(hasattr(bridge, name) for name in ("model", "backend", "invoker", "process"))
    assert not any(hasattr(session, name) for name in ("model", "generate", "invoke"))
    serving.close()
    with pytest.raises(ProductionServingInferenceError, match="current_serving_session_required"):
        bridge.generate(prompt="x", caller="operator", correlation_id="inference-2")


def test_authority_digest_mismatch_fails_before_generation(monkeypatch, tmp_path):
    bridge, _, session, model, _, _ = setup(monkeypatch, tmp_path)
    binding = {**session.binding, "authority_map_digest": "substituted"}
    with pytest.raises(ProductionServingInferenceError, match="authority_map_digest_mismatch"):
        bridge._authority(ServingSession(session.session_id, MappingProxyType(binding)))
    assert model.calls == 0


def test_stable_conversation_identity_excludes_serving_lifetime(monkeypatch, tmp_path):
    bridge, _, session, _, _, _ = setup(monkeypatch, tmp_path)
    identity = bridge.current_conversation_model_identity()
    assert identity["activation_state_semantic_digest"] == session.binding["activation_state_semantic_digest"]
    assert "serving_session_id" not in identity and "serving_operation_id" not in identity


def test_caller_linkage_is_namespaced_and_cannot_override_serving_evidence(monkeypatch, tmp_path):
    bridge, _, session, _, _, _ = setup(monkeypatch, tmp_path)
    supplied = {"session_id": "conversation", "serving_session_id": "forged", "runtime_id": "forged"}
    receipt = bridge.generate(prompt="hello", caller="chat", correlation_id="caller-linkage", caller_linkage=supplied)
    linkage = receipt.request["linkage"]
    assert linkage["serving_session_id"] == session.session_id
    assert linkage["runtime_id"] == session.binding["runtime_id"]
    assert linkage["caller_context"] == supplied
