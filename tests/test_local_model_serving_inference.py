from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import threading
import time
from types import MappingProxyType, SimpleNamespace

import pytest

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import (
    AdmissionOutcome, AuthorityClass, ControlPlaneKernel,
)
from sentientos.governed_local_model_invocation import LocalModelInvocationBudget
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_model_authority import build_local_model_authority_map, digest_payload
from sentientos.local_model_production_serving import ProductionServingController, ServingSession
from sentientos.local_model_serving_inference import (
    ProductionServingInferenceController,
    ProductionServingInferenceError,
)
from tests.test_governed_local_model_resource_invocation_composition import (
    setup as resource_allocation_setup,
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
    from sentientos.governed_local_model_invocation import LocalModelInvocationBudget
    from sentientos.governed_local_model_resource_allocation import (
        GovernedLocalModelResourceBounds,
        GovernedLocalModelResourcePolicy,
    )
    from sentientos.production_chat_resource_provisioning import (
        load_production_chat_resource_context_owner,
    )
    from sentientos.production_chat_resource_provisioning_bundle_producer import (
        produce_production_chat_resource_provisioning_bundle,
    )
    from tests.test_gaming_companion_tls_transport import _certificate_bundle
    from tests.test_production_chat_resource_provisioning_bundle_producer import (
        encoded, inputs as provisioning_inputs,
    )

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

    resource_registry, provisioning_artifacts = provisioning_inputs(
        tmp_path / "resource-provisioning", calls=2)
    resource_bounds = GovernedLocalModelResourceBounds(8000, 4000, 512, 30.0, 2)
    resource_policy = GovernedLocalModelResourcePolicy.create(
        epoch=1, max_resource_specific_bounds=resource_bounds,
        not_before="2026-09-21T08:00:00Z",
        valid_until="2026-09-21T09:15:00Z")
    provisioning_artifacts["requested_bounds"] = resource_bounds
    provisioning_artifacts["resource_policy_artifact"] = encoded(
        resource_policy.to_dict())
    bundle = produce_production_chat_resource_provisioning_bundle(
        resource_registry, "game-priority", **provisioning_artifacts)
    resource_context_owner = load_production_chat_resource_context_owner(
        resource_registry, "game-priority",
        clock=lambda: "2026-09-21T08:30:00Z",
        nonce_source=lambda: "deferred-game-priority-attempt")
    assert resource_context_owner.allocator.ledger.remaining_calls(
        bundle.allocation_id) == 2
    bridge, serving, _, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, foreground_game_detector=detector,
        host_resource_observation_owner=host_resource_owner)
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
    try:
        prompt = ("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
            "[SESSION_HISTORY_DATA]\nUSER_DATA: hello")
        receipt = bridge.generate(prompt=prompt, caller="chat_service",
            correlation_id="mtls-game-host-pressure",
            budget=LocalModelInvocationBudget(8000, 4000, 512, 30.0, 2),
            resource_context=resource_context_owner.next_context())
        assert receipt.status == "deferred"
        assert model.calls == 0
        assert model.closed is True
        assert serving.current_session() is None
        resource_ledger = resource_context_owner.allocator.ledger
        assert resource_ledger.snapshot_counts() == (1, 0, 0)
        assert resource_ledger.remaining_calls(bundle.allocation_id) == 2
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
        assert release["resource_measurement_comparison"]["status"] == "comparable"
        assert release["resource_measurement_comparison"][
            "ram_utilization_delta_percentage_points"] == 0.0
        assert release["resource_measurement_comparison"]["interpretation"] == (
            "sample_delta_only; telemetry_does_not_establish_causation")
    finally:
        resource_context_owner.close()
        detector.close()
        serving.close()


@pytest.mark.parametrize("gpu_observation", ["pressure", "unavailable"])
def test_automatic_game_detection_unavailable_keeps_gpu_inference_deferred(
        monkeypatch, tmp_path, gpu_observation):
    """Conservative automatic gaming mode must honor observed host pressure."""
    from datetime import datetime, timezone

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
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
            HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
                (collector("nvidia_gpu", device_count=1, devices=[{
                    "index": 0, "gpu_utilization_percent": 96.0,
                    "vram_utilization_percent": 91.0}]) if gpu_observation == "pressure"
                 else lambda *, observed_at=None: HostCollectorResult(
                    "nvidia_gpu", "unavailable", observed_at or now.isoformat(),
                    "synthetic_test_fixture"))),
        ]), clock=lambda: now.isoformat())

    class UnavailableGameDetector:
        def observe(self, _process_names):
            return ForegroundGameObservation("unavailable", None, None,
                now.isoformat())

    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel,
        foreground_game_detector=UnavailableGameDetector(),
        host_resource_observation_owner=host_owner, gpu_layers=24)
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
    try:
        receipt = bridge.generate(
            prompt=("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
                "[SESSION_HISTORY_DATA]\nUSER_DATA: optional request"),
            caller="chat_service", correlation_id="automatic-game-observation-unavailable")

        assert receipt.status == "deferred"
        assert model.calls == 0
        assert model.closed is False
        assert serving.current_session() == session
        assert host_owner.collector_call_count == 3
        workload = receipt.request["linkage"]["workload_evidence"]
        assert workload["configured_mode"] == "automatic"
        assert workload["mode_source"] == (
            "foreground_observation_unavailable_conservative_gaming")
        assert workload["observation_status"] == "unavailable"
        decisions = [json.loads(line) for line in
            (tmp_path / "kernel-decisions.jsonl").read_text(
                encoding="utf-8").splitlines()]
        inference_decision = next(item for item in decisions
            if item.get("action_kind") == "local_model_inference")
        delegated = inference_decision["delegated_outcomes"]["runtime_governor"]
        assert delegated["reason"] == (
            "deferred_local_model_inference_under_host_pressure_in_conservative_automatic_mode"
            if gpu_observation == "pressure" else
            "deferred_resource_telemetry_incomplete_in_conservative_automatic_mode")
        assert delegated["evidence_refs"]["host_resource_evidence"]["status"] == "current"
        if gpu_observation == "pressure":
            assert delegated["evidence_refs"]["observed_pressure_labels"] == ["gpu_pressure"]
        else:
            assert delegated["evidence_refs"]["host_resource_evidence"][
                "gpu_telemetry_complete"] is False
        assert delegated["evidence_refs"]["game_workload_evidence"]["status"] == "unavailable"
    finally:
        serving.close()


@pytest.mark.parametrize(("pressure_kind", "gpu_layers", "expected_status",
    "expected_reason"), [
    ("gpu", 24, "deferred",
        "deferred_gpu_backed_local_model_inference_under_gpu_pressure"),
    ("gpu", 0, "admitted_completed", "allowed"),
    ("memory", 24, "deferred",
        "deferred_local_model_inference_under_memory_pressure"),
    ("memory", 0, "deferred",
        "deferred_local_model_inference_under_memory_pressure"),
    ("cpu", 24, "deferred",
        "deferred_local_model_inference_under_cpu_pressure"),
    ("cpu", 0, "deferred",
        "deferred_local_model_inference_under_cpu_pressure"),
    ("thermal", 24, "deferred",
        "deferred_local_model_inference_under_thermal_pressure"),
    ("thermal", 0, "deferred",
        "deferred_local_model_inference_under_thermal_pressure"),
])
def test_current_host_pressure_defers_optional_foreground_inference_by_resource_route(
        monkeypatch, tmp_path, pressure_kind, gpu_layers, expected_status,
        expected_reason):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
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
                collector("cpu", utilization_percent=(96.0 if pressure_kind == "cpu"
                    else 20.0))),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=(96.0 if pressure_kind == "memory"
                    else 40.0))),
            HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
                collector("nvidia_gpu", device_count=1, devices=[{
                    "index": 0,
                    "gpu_utilization_percent": 96.0 if pressure_kind == "gpu" else 20.0,
                    "vram_utilization_percent": 91.0 if pressure_kind == "gpu" else 30.0,
                    "temperature_c": 92.0 if pressure_kind == "thermal" else 55.0}])),
        ]), clock=lambda: now.isoformat())
    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        gpu_layers=gpu_layers)
    _, _, _, resource_context, resource_ledger = resource_allocation_setup(
        tmp_path / "resource-allocation", calls=2, max_input_chars=8192)
    monkeypatch.setattr(
        "sentientos.governed_local_model_invocation._verified_model_execution_profile",
        lambda *_: {
            "schema_version": "sentientos.model_execution_profile:v1",
            "engine": "llama_cpp",
            "accelerator_route": "gpu" if gpu_layers else "cpu",
            "gpu_layers": gpu_layers,
            "configuration_digest": "a" * 64,
        })
    try:
        receipt = bridge.generate(
            prompt=("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
                "[SESSION_HISTORY_DATA]\nUSER_DATA: optional request"),
            caller="chat_service", correlation_id="foreground-resource-pressure",
            budget=LocalModelInvocationBudget(8192, 200, 20, 5.0, 2),
            resource_context=resource_context)

        assert receipt.status == expected_status
        assert model.calls == (1 if expected_status == "admitted_completed" else 0)
        assert serving.current_session() == session
        assert resource_ledger.remaining_calls(
            resource_context.allocation.allocation_id) == (
                1 if expected_status == "admitted_completed" else 2)
        assert resource_ledger.snapshot_counts() == (
            (1, 1, 3) if expected_status == "admitted_completed" else (1, 0, 0))
        decisions = [json.loads(line) for line in
            (tmp_path / "kernel-decisions.jsonl").read_text(
                encoding="utf-8").splitlines()]
        inference_decision = next(item for item in decisions
            if item.get("action_kind") == "local_model_inference")
        delegated = inference_decision["delegated_outcomes"]["runtime_governor"]
        assert delegated["evidence_refs"]["host_resource_evidence"]["status"] == "current"
        expected_label = f"{pressure_kind}_pressure"
        assert delegated["evidence_refs"]["observed_pressure_labels"] == [expected_label]
        assert delegated["reason"] == expected_reason
        if expected_status == "deferred":
            assert receipt.output_text is None
            assert delegated["evidence_refs"]["host_resource_evidence"][
                "ram_utilization_percent"] == (96.0 if pressure_kind == "memory" else 40.0)
            assert delegated["evidence_refs"]["host_resource_evidence"][
                "cpu_utilization_percent"] == (96.0 if pressure_kind == "cpu" else 20.0)
            if pressure_kind == "thermal":
                assert delegated["evidence_refs"]["host_resource_evidence"][
                    "thermal_zone_temperatures_c"] == {"nvidia_gpu_0": 92.0}
        else:
            assert receipt.output_text == "answer"
    finally:
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
          kernel_override=None, host_resource_observation_owner=None, gpu_layers=0,
          serving_admission_context_provider=None, model_factory=None):
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
    kernel = kernel_override or Kernel(inference)
    model = Model(identity, on_generate)
    factory = model_factory(identity, model) if model_factory is not None else (lambda c, l: model)
    serving = ProductionServingController(handle, kernel, model_factory=factory)
    monkeypatch.setattr(serving, "_commissioning_identity", lambda s: identity.to_dict())
    session = serving.establish(operation_id=serving_operation_id,
        admission_context_provider=serving_admission_context_provider)
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


@pytest.mark.parametrize("mode", ["normal", "automatic"])
def test_resource_reconciliation_accelerates_during_active_inference(
        monkeypatch, tmp_path, mode):
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
    if mode == "automatic":
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
    ("normal", "deferred", 0),
    ("gaming", "deferred", 0),
])
def test_normal_and_gaming_profiles_defer_under_host_cpu_pressure(
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
        assert delegated["reason"] == (
            "deferred_local_model_inference_under_cpu_pressure")
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


@pytest.mark.parametrize(("cpu_percent", "gpu_layers", "expected_status",
                         "expected_closed", "expected_trigger"), [
    (95.0, 24, "worker_closed", True, "idle_gaming_profile_gpu_residency"),
    (95.0, 0, "worker_closed", True, "gaming_profile_resource_reconciliation"),
    (20.0, 24, "worker_closed", True, "idle_gaming_profile_gpu_residency"),
    (20.0, 0, "skipped", False, None),
])
def test_selected_gaming_profile_releases_gpu_model_under_pressure_or_for_residency(
        monkeypatch, tmp_path, cpu_percent, gpu_layers, expected_status,
        expected_closed, expected_trigger):
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
        gpu_layers=gpu_layers)
    reconciliation_wakeup = threading.Event()
    bridge.set_resource_reconciliation_wakeup(reconciliation_wakeup.set)
    bridge.set_workload_mode("gaming")
    assert reconciliation_wakeup.is_set()

    result = bridge.reconcile_idle_game_resource_state()

    assert result["status"] == expected_status
    assert model.closed is expected_closed
    if expected_closed:
        assert serving.current_session() is None
        assert result["trigger_kind"] == expected_trigger
        assert isinstance(result["release_receipt_id"], str)
        release_files = list((tmp_path / "state" / "installations" / "install-1" /
            "state" / "local-model" / "serving" /
            "resource-release-receipts").glob("*.json"))
        assert len(release_files) == 1
        receipt = json.loads(release_files[0].read_text(encoding="utf-8"))
        assert receipt["status"] == "worker_closed"
        assert receipt["inference_performed"] is False
        assert receipt["host_mutation_performed"] is False
        decision = next(json.loads(line) for line in reversed(
            (tmp_path / "kernel-decisions.jsonl").read_text(
                encoding="utf-8").splitlines())
            if json.loads(line).get("action_kind") == "local_model_resource_release")
        delegated = decision["delegated_outcomes"]["runtime_governor"]
        assert delegated["allowed"] is True
        assert delegated["reason"] == "model_resource_release_fail_safe"
        evidence = delegated["evidence_refs"]["resource_observation_evidence"]
        if expected_trigger == "gaming_profile_resource_reconciliation":
            assert receipt["resource_observation"]["workload_mode"] == "gaming"
            assert receipt["resource_observation"]["workload_mode_source"] == "operator_selected"
            assert "game_workload_message_id" not in receipt["resource_observation"]
            assert evidence["status"] == "current"
            assert evidence["workload_mode"] == "gaming"
            assert evidence["workload_mode_source"] == "operator_selected"
            assert evidence["pressure_labels"] == ["cpu_pressure"]
        else:
            assert receipt["resource_observation"]["workload_mode"] == "gaming"
            assert receipt["resource_observation"]["workload_mode_source"] == "operator_selected"
            assert receipt["resource_observation"]["host_telemetry_used_for_admission"] is False
            assert receipt["resource_measurement_comparison"]["before_sample_kind"] == "unavailable"
            assert evidence["status"] == "current"
            assert evidence["workload_mode"] == "gaming"
            assert evidence["model_gpu_layers"] == gpu_layers
    else:
        assert result["reason"] == "current_host_pressure_evidence_required"
        assert serving.current_session() == session
        assert list((tmp_path / "state" / "installations" / "install-1" /
            "state" / "local-model" / "serving" /
            "resource-release-receipts").glob("*.json")) == []
        serving.close()


@pytest.mark.parametrize(("cpu_percent", "expected_status"), [
    (95.0, "worker_closed"),
    (20.0, "skipped"),
])
def test_conservative_automatic_profile_releases_resident_model_only_under_host_pressure(
        monkeypatch, tmp_path, request, cpu_percent, expected_status):
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

    source_key = b"automatic-idle-release-game-source-key"
    acknowledgment_key = b"automatic-idle-release-core-ack-key"
    source_id = "idle-release-game-edge"
    generation_id = "idle-release-game-generation-1"
    runtime = CompanionBridgeLoopbackRuntime(
        receiver=CompanionBridgeReceiver(source_keys={source_id: source_key},
            expected_generations={source_id: generation_id}),
        acknowledgment_source_id="sentientos-core",
        acknowledgment_generation_id="sentientos-core-generation-1",
        acknowledgment_key=acknowledgment_key)
    runtime.start()
    detector = BridgeForegroundGameDetector(runtime=runtime,
        source_id=source_id, generation_id=generation_id,
        max_observation_age_seconds=5)
    request.addfinalizer(detector.close)
    detector.set_game_workload_admission_owner(kernel)

    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, foreground_game_detector=detector,
        host_resource_observation_owner=host_owner, gpu_layers=24)
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])

    result = bridge.reconcile_idle_game_resource_state()

    assert result["status"] == expected_status
    assert host_owner.collector_call_count == (4 if expected_status == "worker_closed" else 2)
    if expected_status == "worker_closed":
        assert model.closed is True
        assert serving.current_session() is None
        assert result["trigger_kind"] == (
            "conservative_automatic_gaming_resource_reconciliation")
        receipt_path = next((tmp_path / "state" / "installations" / "install-1" /
            "state" / "local-model" / "serving" / "resource-release-receipts").glob("*.json"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        evidence = receipt["resource_observation"]
        assert evidence["configured_mode"] == "automatic"
        assert evidence["workload_mode"] == "gaming"
        assert evidence["workload_mode_source"] == (
            "foreground_observation_unavailable_conservative_gaming")
        assert evidence["workload_observation_status"] == "bridge_observation_unavailable"
        assert "game_workload_message_id" not in evidence
        assert receipt["inference_performed"] is False
        assert receipt["host_mutation_performed"] is False
        decisions = [json.loads(line) for line in
            (tmp_path / "kernel-decisions.jsonl").read_text(
                encoding="utf-8").splitlines()]
        release = next(item for item in decisions
            if item.get("action_kind") == "local_model_resource_release")
        delegated = release["delegated_outcomes"]["runtime_governor"]
        assert delegated["allowed"] is True
        assert delegated["reason"] == "model_resource_release_fail_safe"
        observed = delegated["evidence_refs"]["resource_observation_evidence"]
        assert observed["status"] == "current"
        assert observed["configured_mode"] == "automatic"
        assert observed["workload_observation_status"] == "bridge_observation_unavailable"
    else:
        assert model.closed is False
        assert serving.current_session() == session
        assert result["reason"] == "current_host_pressure_evidence_required"
        receipt_dir = (tmp_path / "state" / "installations" / "install-1" /
            "state" / "local-model" / "serving" / "resource-release-receipts")
        assert list(receipt_dir.glob("*.json")) == []
        serving.close()


@pytest.mark.parametrize(("gpu_percent", "vram_percent", "ram_percent",
    "gpu_layers", "expected_status", "expected_trigger"), [
    (94.0, 92.0, 40.0, 24, "worker_closed",
        "idle_host_gpu_resource_reconciliation"),
    (20.0, 30.0, 40.0, 24, "skipped", None),
    (20.0, 30.0, 94.0, 0, "worker_closed",
        "idle_host_memory_resource_reconciliation"),
    (20.0, 30.0, 40.0, 0, "skipped", None),
])
def test_normal_mode_releases_only_idle_residency_under_host_pressure(
        monkeypatch, tmp_path, gpu_percent, vram_percent, ram_percent, gpu_layers,
        expected_status, expected_trigger):
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
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=ram_percent)),
            HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
                collector("nvidia_gpu", device_count=1, devices=[{
                    "index": 0, "gpu_utilization_percent": gpu_percent,
                    "vram_utilization_percent": vram_percent}]))
        ]), clock=lambda: now.isoformat())
    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        gpu_layers=gpu_layers)
    import asyncio
    from sentientos import chat_service

    reconciliations = []
    state_after_reconciliation = []
    reconciliation_finished = threading.Event()

    def reconcile():
        result = bridge.reconcile_idle_game_resource_state()
        reconciliations.append(result)
        state_after_reconciliation.append(
            (model.closed, serving.current_session() == session))
        reconciliation_finished.set()
        return result

    service = SimpleNamespace(
        reconcile_workload_state=reconcile,
        resource_reconciliation_interval_seconds=(
            bridge.resource_reconciliation_interval_seconds),
        set_resource_reconciliation_wakeup=(bridge.set_resource_reconciliation_wakeup),
        close_outputs=lambda: None)
    previous_composition = chat_service._PRODUCTION_COMPOSITION
    previous_reconciliation_task = chat_service._RESOURCE_RECONCILIATION_TASK
    chat_service._PRODUCTION_COMPOSITION = chat_service.ProductionChatComposition(
        service, serving)
    chat_service._RESOURCE_RECONCILIATION_TASK = None

    async def run_scheduler():
        await chat_service._startup_event()
        try:
            if not await asyncio.to_thread(reconciliation_finished.wait, 5):
                raise AssertionError("scheduled normal-mode resource reconciliation did not run")
            return chat_service._RESOURCE_RECONCILIATION_TASK is not None
        finally:
            await chat_service._shutdown_event()

    try:
        scheduler_started = asyncio.run(run_scheduler())
    finally:
        chat_service._PRODUCTION_COMPOSITION = previous_composition
        chat_service._RESOURCE_RECONCILIATION_TASK = previous_reconciliation_task
    result = reconciliations[0]

    assert scheduler_started is True
    assert result["status"] == expected_status, result
    assert host_owner.collector_call_count == (
        6 if expected_status == "worker_closed" else 3)
    if expected_status == "worker_closed":
        assert state_after_reconciliation == [(True, False)]
        assert result["trigger_kind"] == expected_trigger
        release_path = next((tmp_path / "state" / "installations" / "install-1" /
            "state" / "local-model" / "serving" /
            "resource-release-receipts").glob("*.json"))
        receipt = json.loads(release_path.read_text(encoding="utf-8"))
        evidence = receipt["resource_observation"]
        if expected_trigger == "idle_host_gpu_resource_reconciliation":
            assert evidence["pressure_labels"] == ["gpu_pressure"]
            assert evidence["model_gpu_layers"] == 24
        else:
            assert evidence["pressure_labels"] == ["memory_pressure"]
            assert evidence["ram_utilization_percent"] == 94.0
            assert evidence["model_gpu_layers"] == 0
            comparison = receipt["resource_measurement_comparison"]
            assert comparison["before"]["ram_utilization_percent"] == 94.0
            assert comparison["after"]["ram_utilization_percent"] == 94.0
            assert comparison["ram_utilization_delta_percentage_points"] == 0.0
        assert evidence["active_inference_preemption_requested"] is False
        assert receipt["inference_performed"] is False
        assert receipt["host_mutation_performed"] is False
        decisions = [json.loads(line) for line in
            (tmp_path / "kernel-decisions.jsonl").read_text(
                encoding="utf-8").splitlines()]
        release = next(item for item in decisions
            if item.get("action_kind") == "local_model_resource_release")
        delegated = release["delegated_outcomes"]["runtime_governor"]
        assert delegated["allowed"] is True
        assert delegated["reason"] == "model_resource_release_fail_safe"
        assert delegated["evidence_refs"]["resource_observation_evidence"][
            "status"] == "current"
        if expected_trigger == "idle_host_memory_resource_reconciliation":
            assert delegated["evidence_refs"]["resource_observation_evidence"][
                "ram_utilization_percent"] == 94.0
    else:
        assert state_after_reconciliation == [(False, True)]
        assert result["reason"] == ("current_host_gpu_pressure_required"
            if gpu_layers else "current_host_memory_pressure_required")


def test_gaming_profile_switch_cancels_active_optional_gpu_inference(monkeypatch, tmp_path):
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
                collector("cpu", utilization_percent=25.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
            HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
                collector("nvidia_gpu", device_count=1, devices=[{
                    "index": 0, "gpu_utilization_percent": 20.0,
                    "vram_utilization_percent": 35.0}])),
        ]), clock=lambda: now.isoformat())
    started = threading.Event()
    cancelled = threading.Event()

    def active_generation():
        started.set()
        if not cancelled.wait(timeout=5):
            raise AssertionError("gaming-profile cancellation was not delivered")
        raise RuntimeError("fixture_generation_cancelled_for_gaming_profile")

    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        gpu_layers=24, on_generate=active_generation)
    model.cancel_pending_generation = lambda: (cancelled.set() or True)
    inference_result = {}
    invocation = threading.Thread(target=lambda: inference_result.setdefault(
        "receipt", bridge.generate(prompt="optional chat work", caller="operator",
            correlation_id="gaming-profile-active-inference")))

    import asyncio
    from sentientos import chat_service
    from types import SimpleNamespace

    reconciliations = []
    service = SimpleNamespace(
        reconcile_workload_state=lambda: reconciliations.append(
            bridge.reconcile_workload_state()) or reconciliations[-1],
        resource_reconciliation_interval_seconds=(
            bridge.resource_reconciliation_interval_seconds),
        set_resource_reconciliation_wakeup=(bridge.set_resource_reconciliation_wakeup),
        close_outputs=lambda: None)
    previous_composition = chat_service._PRODUCTION_COMPOSITION
    previous_reconciliation_task = chat_service._RESOURCE_RECONCILIATION_TASK
    chat_service._PRODUCTION_COMPOSITION = chat_service.ProductionChatComposition(
        service, serving)
    chat_service._RESOURCE_RECONCILIATION_TASK = None

    async def run_reconciliation_scheduler():
        await chat_service._startup_event()
        try:
            invocation.start()
            if not await asyncio.to_thread(started.wait, 5):
                raise AssertionError("active inference did not start")
            bridge.set_workload_mode("gaming")
            if not await asyncio.to_thread(cancelled.wait, 5):
                raise AssertionError("scheduler did not cancel gaming-profile inference")
            assert bridge.resource_reconciliation_interval_seconds() == 0.5
            await asyncio.to_thread(invocation.join, 5)
            assert not invocation.is_alive()
            return (chat_service._RESOURCE_RECONCILIATION_TASK is not None,
                serving.current_session() == session, model.closed)
        finally:
            await chat_service._shutdown_event()

    try:
        scheduler_started = asyncio.run(run_reconciliation_scheduler())
    finally:
        chat_service._PRODUCTION_COMPOSITION = previous_composition
        chat_service._RESOURCE_RECONCILIATION_TASK = previous_reconciliation_task

    assert not invocation.is_alive()
    assert scheduler_started == (True, False, True)
    assert any(item.get("trigger_kind") == "idle_gaming_profile_gpu_residency"
        for item in reconciliations)
    reconciliation = next(item for item in reconciliations
        if item.get("trigger_kind") == "idle_gaming_profile_gpu_residency")
    assert reconciliation["status"] == "worker_closed"
    assert reconciliation["trigger_kind"] == "idle_gaming_profile_gpu_residency"
    assert reconciliation["active_inference_cancellation_confirmed"] is True
    assert inference_result["receipt"].status == "cancelled"
    assert inference_result["receipt"].output_text is None
    assert model.closed is True
    assert model.calls == 1
    assert serving.current_session() is None
    release_path = next((tmp_path / "state" / "installations" / "install-1" /
        "state" / "local-model" / "serving" / "resource-release-receipts").glob("*.json"))
    release = json.loads(release_path.read_text(encoding="utf-8"))
    assert release["active_inference_preemption_requested"] is True
    assert release["active_inference_cancellation_confirmed"] is True
    assert release["resource_observation"]["workload_mode"] == "gaming"
    assert release["resource_observation"]["workload_mode_source"] == "operator_selected"
    assert "game_workload_message_id" not in release["resource_observation"]
    decision = next(json.loads(line) for line in reversed(
        (tmp_path / "kernel-decisions.jsonl").read_text(
            encoding="utf-8").splitlines())
        if json.loads(line).get("action_kind") == "local_model_resource_release")
    delegated = decision["delegated_outcomes"]["runtime_governor"]
    assert delegated["allowed"] is True
    assert delegated["reason"] == "model_resource_release_fail_safe"
    assert delegated["evidence_refs"]["resource_observation_evidence"][
        "active_inference_preemption_requested"] is True


def test_conservative_automatic_host_pressure_cancels_active_optional_inference(
        monkeypatch, tmp_path, request):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    host_pressure = [False]

    def collector(collector_id, **values):
        def collect(*, observed_at=None):
            collected_values = dict(values)
            if collector_id == "cpu":
                collected_values["utilization_percent"] = (
                    95.0 if host_pressure[0] else 20.0)
            return HostCollectorResult(collector_id, "available",
                observed_at or now.isoformat(), "synthetic_test_fixture",
                values=collected_values)
        return collect

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
            HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
                collector("nvidia_gpu", device_count=1, devices=[{
                    "index": 0, "gpu_utilization_percent": 20.0,
                    "vram_utilization_percent": 35.0}])),
        ]), clock=lambda: now.isoformat())

    source_key = b"automatic-recovery-game-source-key-material"
    acknowledgment_key = b"automatic-recovery-core-acknowledgment-key"
    source_id = "recovery-game-edge"
    generation_id = "recovery-game-generation-1"
    runtime = CompanionBridgeLoopbackRuntime(
        receiver=CompanionBridgeReceiver(source_keys={source_id: source_key},
            expected_generations={source_id: generation_id}),
        acknowledgment_source_id="sentientos-core",
        acknowledgment_generation_id="sentientos-core-generation-1",
        acknowledgment_key=acknowledgment_key, queue_capacity=2)
    port = runtime.start()
    detector = BridgeForegroundGameDetector(runtime=runtime,
        source_id=source_id, generation_id=generation_id,
        max_observation_age_seconds=5)
    request.addfinalizer(detector.close)
    detector.set_game_workload_admission_owner(kernel)
    bridge_client = CompanionBridgeLoopbackClient(port=port,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"sentientos-core": acknowledgment_key},
            expected_generations={"sentientos-core": "sentientos-core-generation-1"}),
        timeout_seconds=1.0)

    class DesktopObservation:
        def observe(self, _process_names):
            return ForegroundGameObservation("available", False,
                hashlib.sha256(b"desktop.exe").hexdigest(),
                datetime.now(timezone.utc).isoformat(),
                game_process_running=False, running_process_name_digests=())

    publisher = WindowsForegroundBridgePublisher(detector=DesktopObservation(),
        client=bridge_client, source_id=source_id,
        session_id="automatic-recovery-session-1", generation_id=generation_id,
        source_key=source_key)
    bridge_holder = {}

    def serving_resource_context(correlation_id, activation_state):
        observation_id = "local-chat-serving-" + hashlib.sha256(
            correlation_id.encode("utf-8")).hexdigest()[:32]
        host_owner.run_cycle(correlation_id=observation_id)
        if "bridge" in bridge_holder:
            workload = bridge_holder["bridge"].current_workload_state()
        else:
            workload = {"configured_mode": "normal", "effective_mode": "normal",
                "mode_source": "operator_selected",
                "observation_status": "not_requested", "game_foreground": None,
                "game_process_running": None, "observed_at": None,
                "transport_provenance": None}
        load_configuration = activation_state.get("load_configuration")
        gpu_layers = (load_configuration.get("n_gpu_layers")
            if isinstance(load_configuration, Mapping) else None)
        profile_layers = (gpu_layers if type(gpu_layers) is int
            and 0 <= gpu_layers <= 256 else None)
        model_execution_profile = {
            "schema_version": "sentientos.model_execution_profile:v1",
            "engine": "llama_cpp",
            "accelerator_route": ("gpu" if profile_layers else
                "cpu" if profile_layers == 0 else "unknown"),
            "gpu_layers": profile_layers,
            "configuration_digest": digest_payload(
                dict(load_configuration) if isinstance(load_configuration, Mapping) else {}),
        }
        return {
            "resource_governance_required": True,
            "purpose": "local_model_serving",
            "host_resource_observation_namespace": "local-chat-serving",
            "host_resource_observation_id": observation_id,
            "model_execution_profile": model_execution_profile,
            "workload_mode": workload.get("configured_mode"),
            "effective_workload_mode": workload.get("effective_mode"),
            "serving_workload_evidence": {key: workload.get(key) for key in (
                "configured_mode", "mode_source", "observation_status",
                "game_foreground", "game_process_running", "observed_at",
                "transport_provenance")},
        }

    models = []

    def model_factory(identity, initial_model):
        models.append(initial_model)
        initial_pending = [True]
        def create(_config, _load):
            if initial_pending[0]:
                initial_pending[0] = False
                return initial_model
            model = Model(identity)
            models.append(model)
            return model
        return create

    started = threading.Event()
    cancelled = threading.Event()

    def active_generation():
        started.set()
        if not cancelled.wait(timeout=5):
            raise AssertionError("conservative automatic host-pressure cancellation was not delivered")
        raise RuntimeError("fixture_generation_cancelled_for_conservative_automatic_pressure")

    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, foreground_game_detector=detector,
        host_resource_observation_owner=host_owner, gpu_layers=24,
        on_generate=active_generation,
        serving_admission_context_provider=serving_resource_context,
        model_factory=model_factory)
    bridge_holder["bridge"] = bridge
    model.cancel_pending_generation = lambda: (cancelled.set() or True)
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
    inference_result = {}
    def invoke_optional_work():
        try:
            inference_result["receipt"] = bridge.generate(
                prompt=("[SYSTEM_INSTRUCTION]\nRules.\n"
                    "[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\nUSER_DATA: optional work"),
                caller="operator",
                correlation_id="conservative-automatic-active-inference")
        except Exception as exc:
            inference_result["error"] = f"{type(exc).__name__}:{exc}"

    invocation = threading.Thread(target=invoke_optional_work)
    import asyncio
    from sentientos import chat_service
    from types import SimpleNamespace

    reconciliations = []
    service = SimpleNamespace(
        reconcile_workload_state=lambda: reconciliations.append(
            bridge.reconcile_workload_state()) or reconciliations[-1],
        resource_reconciliation_interval_seconds=(
            bridge.resource_reconciliation_interval_seconds),
        set_resource_reconciliation_wakeup=(bridge.set_resource_reconciliation_wakeup),
        close_outputs=lambda: None)
    previous_composition = chat_service._PRODUCTION_COMPOSITION
    previous_reconciliation_task = chat_service._RESOURCE_RECONCILIATION_TASK
    composition = chat_service.ProductionChatComposition(service, serving)
    chat_service._PRODUCTION_COMPOSITION = composition
    chat_service._RESOURCE_RECONCILIATION_TASK = None
    recovery_results = {}

    async def run_reconciliation_scheduler():
        await chat_service._startup_event()
        try:
            invocation.start()
            assert await asyncio.to_thread(started.wait, 5), {
                "status": getattr(inference_result.get("receipt"), "status", None),
                "request": getattr(inference_result.get("receipt"), "request", None),
                "error": inference_result.get("error")}
            host_pressure[0] = True
            assert await asyncio.to_thread(cancelled.wait, 5), sorted({
                item.get("reason") for item in reconciliations})
            assert bridge.resource_reconciliation_interval_seconds() == 0.5
            await asyncio.to_thread(invocation.join, 5)
            assert not invocation.is_alive()
            deferred = await asyncio.to_thread(composition.reconcile_workload_state)
            recovery_results["automatic"] = deferred["serving_recovery"]
            assert recovery_results["automatic"]["status"] == "deferred"
            assert serving.current_session() is None
            assert serving.resource_recovery_pending() is True

            host_pressure[0] = False
            inactive_message = publisher.publish_once(("ExampleGame.exe",))
            restored = await asyncio.to_thread(composition.reconcile_workload_state)
            recovery_results["automatic_restored"] = restored["serving_recovery"]
            recovered_session = serving.current_session()
            assert recovery_results["automatic_restored"]["status"] == "restored"
            assert recovered_session is not None and recovered_session != session
            recovery_results["model_is_current"] = models[1].closed is False
            recovery_results["pending_cleared"] = not serving.resource_recovery_pending()
            receipt_path = (tmp_path / "state" / "installations" / "install-1" /
                "state" / "local-model" / "serving" / "receipts" /
                (recovered_session.binding["serving_receipt_id"] + ".json"))
            recovered_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            recovery_results["admitted_workload_message_id"] = (
                recovered_receipt["resource_admission_context"][
                    "serving_workload_evidence"]["transport_provenance"]["message_id"])
            recovery_results["published_inactive_message_id"] = (
                inactive_message.payload["message_id"])
            return chat_service._RESOURCE_RECONCILIATION_TASK is not None
        finally:
            await chat_service._shutdown_event()

    try:
        scheduler_started = asyncio.run(run_reconciliation_scheduler())
    finally:
        chat_service._PRODUCTION_COMPOSITION = previous_composition
        chat_service._RESOURCE_RECONCILIATION_TASK = previous_reconciliation_task

    assert scheduler_started is True
    assert not invocation.is_alive()
    assert len(reconciliations) >= 2
    assert any(item.get("trigger_kind") == (
        "active_conservative_automatic_gaming_resource_reconciliation")
        for item in reconciliations)
    reconciliation = next(item for item in reconciliations
        if item.get("trigger_kind") ==
        "active_conservative_automatic_gaming_resource_reconciliation")
    try:
        assert reconciliation["status"] == "worker_closed"
        assert reconciliation["trigger_kind"] == (
            "active_conservative_automatic_gaming_resource_reconciliation")
        assert reconciliation["active_inference_cancellation_confirmed"] is True
        assert inference_result["receipt"].status == "cancelled"
        assert inference_result["receipt"].output_text is None
        assert model.closed is True
        assert model.calls == 1
        assert serving.current_session() is None
        release_path = next((tmp_path / "state" / "installations" / "install-1" /
            "state" / "local-model" / "serving" / "resource-release-receipts").glob("*.json"))
        release = json.loads(release_path.read_text(encoding="utf-8"))
        assert release["active_inference_preemption_requested"] is True
        assert release["active_inference_cancellation_confirmed"] is True
        assert release["resource_observation"]["configured_mode"] == "automatic"
        assert release["resource_observation"]["workload_observation_status"] == (
            "bridge_observation_unavailable")
        assert recovery_results["automatic"]["reason_code"] == (
            "model_serving_control_plane_not_allowed")
        assert recovery_results["automatic_restored"]["status"] == "restored"
        assert recovery_results["model_is_current"] is True
        assert recovery_results["pending_cleared"] is True
        assert recovery_results["admitted_workload_message_id"] == (
            recovery_results["published_inactive_message_id"])
        assert len(models) == 2
    finally:
        serving.close()


def test_selected_gaming_profile_cancels_active_cpu_inference_on_host_pressure(
        monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    clock_now = [now]
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    cpu_pressure = [False]

    def collector(collector_id, **values):
        def collect(*, observed_at=None):
            collected_values = dict(values)
            if collector_id == "cpu":
                collected_values["utilization_percent"] = (
                    95.0 if cpu_pressure[0] else 20.0)
            return HostCollectorResult(collector_id, "available",
                observed_at or now.isoformat(), "synthetic_test_fixture",
                values=collected_values)
        return collect

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
        ]), clock=lambda: clock_now[0].isoformat())
    started = threading.Event()
    cancelled = threading.Event()

    def active_generation():
        started.set()
        if not cancelled.wait(timeout=5):
            raise AssertionError("gaming-profile host-pressure cancellation was not delivered")
        raise RuntimeError("fixture_generation_cancelled_for_gaming_profile_host_pressure")

    bridge, serving, _, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        gpu_layers=0, on_generate=active_generation)
    model.cancel_pending_generation = lambda: (cancelled.set() or True)
    bridge.set_workload_mode("gaming")
    result = {}
    invocation = threading.Thread(target=lambda: result.setdefault(
        "receipt", bridge.generate(prompt=("[SYSTEM_INSTRUCTION]\nRules.\n"
            "[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\nUSER_DATA: hello"),
            caller="operator",
            correlation_id="gaming-profile-active-cpu-inference")))
    invocation.start()
    try:
        assert started.wait(timeout=5)
        cpu_pressure[0] = True
        clock_now[0] = now
        reconciliation = bridge.reconcile_workload_state()
        latest = host_owner.latest_evaluation(max_age_seconds=10)
        assert latest is not None
        assert latest.pressure_report.pressure_labels == ("cpu_pressure",)
        assert reconciliation["status"] == "worker_closed", reconciliation
        invocation.join(timeout=5)

        assert not invocation.is_alive()
        assert reconciliation["status"] == "worker_closed"
        assert reconciliation["trigger_kind"] == (
            "active_gaming_profile_resource_reconciliation")
        assert reconciliation["active_inference_cancellation_confirmed"] is True
        assert result["receipt"].status == "cancelled"
        assert result["receipt"].effects["local_model_inference"] is True
        assert model.closed is True
        assert model.calls == 1
        assert serving.current_session() is None
        release_path = next((tmp_path / "state" / "installations" / "install-1" /
            "state" / "local-model" / "serving" / "resource-release-receipts").glob("*.json"))
        release = json.loads(release_path.read_text(encoding="utf-8"))
        assert release["active_inference_preemption_requested"] is True
        assert release["active_inference_cancellation_confirmed"] is True
        assert release["resource_observation"]["workload_mode"] == "gaming"
        assert release["resource_observation"]["pressure_labels"] == ["cpu_pressure"]
        assert release["resource_observation"]["host_report_id"]
        assert release["host_mutation_performed"] is False
        release_decision = next(json.loads(line) for line in reversed(
            (tmp_path / "kernel-decisions.jsonl").read_text(
                encoding="utf-8").splitlines())
            if json.loads(line).get("action_kind") == "local_model_resource_release")
        delegated = release_decision["delegated_outcomes"]["runtime_governor"]
        assert delegated["allowed"] is True
        evidence = delegated["evidence_refs"]["resource_observation_evidence"]
        assert evidence["status"] == "current"
        assert evidence["pressure_labels"] == ["cpu_pressure"]
    finally:
        if invocation.is_alive():
            model.cancel_pending_generation()
            invocation.join(timeout=5)
        serving.close()


def test_normal_host_pressure_cancels_active_optional_inference(
        monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    cpu_pressure = {"active": False}

    def collector(collector_id, **values):
        def collect(*, observed_at=None):
            current = dict(values)
            if collector_id == "cpu":
                current["utilization_percent"] = (
                    95.0 if cpu_pressure["active"] else 20.0)
            return HostCollectorResult(collector_id, "available",
                observed_at or now.isoformat(), "synthetic_test_fixture",
                values=current)
        return collect

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
        ]), clock=lambda: now.isoformat())
    started = threading.Event()
    cancelled = threading.Event()

    def active_generation():
        started.set()
        if not cancelled.wait(timeout=5):
            raise AssertionError("normal host-pressure cancellation was not delivered")
        raise RuntimeError("fixture_generation_cancelled_for_normal_host_pressure")

    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        gpu_layers=0, on_generate=active_generation)
    model.cancel_pending_generation = lambda: (cancelled.set() or True)
    result = {}
    invocation = threading.Thread(target=lambda: result.setdefault(
        "receipt", bridge.generate(prompt=("[SYSTEM_INSTRUCTION]\nRules.\n"
            "[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\nUSER_DATA: hello"),
            caller="operator", correlation_id="normal-host-pressure-active-inference")))
    invocation.start()
    try:
        assert started.wait(timeout=5)
        cpu_pressure["active"] = True
        reconciliation = bridge.reconcile_workload_state()
        invocation.join(timeout=5)

        assert not invocation.is_alive()
        assert reconciliation["status"] == "preempted", reconciliation
        assert reconciliation["trigger_kind"] == (
            "host_resource_pressure_active_inference_preemption")
        assert reconciliation["pressure_labels"] == ["cpu_pressure"]
        assert reconciliation["active_inference_cancellation_confirmed"] is True
        assert reconciliation["model_residency_released"] is False
        assert result["receipt"].status == "cancelled"
        assert result["receipt"].effects["local_model_inference"] is True
        assert model.closed is False
        assert serving.current_session() == session
        assert host_owner.latest_evaluation().pressure_report.pressure_labels == (
            "cpu_pressure",)
        decisions = [json.loads(line) for line in
            (tmp_path / "kernel-decisions.jsonl").read_text(
                encoding="utf-8").splitlines()]
        preemption = next(item for item in reversed(decisions)
            if item.get("action_kind") == "local_model_inference_preemption")
        delegated = preemption["delegated_outcomes"]["runtime_governor"]
        assert delegated["allowed"] is True
        assert delegated["reason"] == (
            "allowed_host_resource_pressure_inference_preemption")
        evidence = delegated["evidence_refs"]["host_resource_evidence"]
        assert evidence["status"] == "current"
        assert evidence["pressure_labels"] == ["cpu_pressure"]
    finally:
        if invocation.is_alive():
            model.cancel_pending_generation()
            invocation.join(timeout=5)
        serving.close()


@pytest.mark.parametrize(("gpu_layers", "cpu_pressure", "game_active"), [
    (24, False, True), (0, True, True), (0, True, False),
], ids=["gpu-game-residency", "cpu-game-pressure", "cpu-normal-host-pressure"])
def test_scheduled_resource_priority_cancels_active_optional_inference(
        monkeypatch, tmp_path, gpu_layers, cpu_pressure, game_active, request):
    import asyncio
    from cryptography import x509
    from sentientos import chat_service
    from sentientos.governed_local_model_invocation import LocalModelInvocationBudget
    from sentientos.governed_local_model_resource_allocation import (
        GovernedLocalModelResourceBounds, GovernedLocalModelResourcePolicy,
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
    from sentientos.foreground_game_bridge import BridgeForegroundGameDetector
    from sentientos.gaming_companion_bridge import CompanionBridgeReceiver
    from sentientos.gaming_companion_tls_transport import (
        CompanionBridgeMutualTLSClient, CompanionBridgeMutualTLSRuntime,
    )
    from sentientos.foreground_game_detection import ForegroundGameDetector
    from tests.test_production_chat_resource_provisioning_bundle_producer import (
        encoded, inputs as provisioning_inputs,
    )
    from tests.test_gaming_companion_tls_transport import _certificate_bundle
    from cryptography.hazmat.primitives.serialization import Encoding

    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "kernel-decisions.jsonl")

    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    server_certificate = x509.load_pem_x509_certificate(
        (tmp_path / "server.pem").read_bytes())
    source_key, ack_key = b"g" * 32, b"a" * 32
    source_id, generation_id = "windows-edge", "edge-cancellation-generation-1"
    bridge_runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1", port=0,
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=CompanionBridgeReceiver(source_keys={source_id: source_key},
            expected_generations={source_id: generation_id}),
        acknowledgment_source_id="wsl-core",
        acknowledgment_generation_id="core-cancellation-generation-1",
        acknowledgment_key=ack_key)
    port = bridge_runtime.start()
    request.addfinalizer(bridge_runtime.close)
    bridge_client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core": ack_key},
            expected_generations={"wsl-core": "core-cancellation-generation-1"}),
        expected_server_certificate_sha256=hashlib.sha256(
            server_certificate.public_bytes(Encoding.DER)).hexdigest())
    presence_publisher = WindowsForegroundBridgePublisher(
        detector=ForegroundGameDetector(system_provider=lambda: "Windows",
            process_name_provider=lambda: "ExampleGame.exe",
            running_process_names_provider=lambda: ("ExampleGame.exe",),
            clock=lambda: now.isoformat()),
        client=bridge_client, source_id=source_id,
        session_id="active-inference-game-presence", generation_id=generation_id,
        source_key=source_key)
    game_detector = BridgeForegroundGameDetector(runtime=bridge_runtime,
        source_id=source_id, generation_id=generation_id, clock=lambda: now)
    game_detector.set_game_workload_admission_owner(kernel)

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    cpu_telemetry = {"utilization_percent": 25.0}
    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                lambda *, observed_at=None: HostCollectorResult("cpu", "available",
                    observed_at or now.isoformat(), "synthetic_test_fixture",
                    values=dict(cpu_telemetry))),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
            HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
                collector("nvidia_gpu", device_count=1, devices=[{
                    "index": 0, "gpu_utilization_percent": 20.0,
                    "vram_utilization_percent": 35.0}])),
        ]), clock=lambda: now.isoformat())
    started = threading.Event()
    cancelled = threading.Event()

    def active_generation():
        started.set()
        if not cancelled.wait(timeout=5):
            raise AssertionError("verified-game cancellation was not delivered")
        raise RuntimeError("fixture_generation_cancelled_for_verified_game")

    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        gpu_layers=gpu_layers, on_generate=active_generation)
    model.cancel_pending_generation = lambda: (cancelled.set() or True)
    installation, provisioning_artifacts = provisioning_inputs(
        tmp_path / "automatic-game-resource-provisioning", calls=2)
    resource_bounds = GovernedLocalModelResourceBounds(8000, 4000, 512, 30.0, 2)
    resource_policy = GovernedLocalModelResourcePolicy.create(
        epoch=1, max_resource_specific_bounds=resource_bounds,
        not_before="2026-09-21T08:00:00Z", valid_until="2026-09-21T09:15:00Z")
    provisioning_artifacts["requested_bounds"] = resource_bounds
    provisioning_artifacts["resource_policy_artifact"] = encoded(resource_policy.to_dict())
    bundle = produce_production_chat_resource_provisioning_bundle(
        installation, "automatic-game-chat", **provisioning_artifacts)
    resource_custody = load_production_chat_resource_context_owner(
        installation, "automatic-game-chat", clock=lambda: "2026-09-21T08:30:00Z",
        nonce_source=iter(("automatic-attempt-one", "automatic-attempt-two")).__next__)
    inference = ResourceBackedProductionChatInference(bridge, resource_custody)
    resource_ledger = resource_custody.allocator.ledger
    reconciliations = []
    service = SimpleNamespace(
        reconcile_workload_state=lambda: reconciliations.append(
            bridge.reconcile_workload_state()) or reconciliations[-1],
        resource_reconciliation_interval_seconds=(
            bridge.resource_reconciliation_interval_seconds),
        set_resource_reconciliation_wakeup=(bridge.set_resource_reconciliation_wakeup),
        close_outputs=lambda: None)
    previous_composition = chat_service._PRODUCTION_COMPOSITION
    previous_reconciliation_task = chat_service._RESOURCE_RECONCILIATION_TASK
    chat_service._PRODUCTION_COMPOSITION = chat_service.ProductionChatComposition(
        service, serving)
    chat_service._RESOURCE_RECONCILIATION_TASK = None
    invocation_result = {}
    game_message_id = {}
    runtime_residency = {}
    active_prompt = ("[SYSTEM_INSTRUCTION]\nRules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
        "[SESSION_HISTORY_DATA]\nUSER_DATA: optional inference")

    def invoke():
        invocation_result["receipt"] = inference.generate(
            prompt=active_prompt, caller="chat_service",
            correlation_id="automatic-game-active-inference",
            budget=LocalModelInvocationBudget(8000, 4000, 512, 30.0, 2),
            caller_linkage={})

    invocation = threading.Thread(target=invoke)

    async def run_reconciliation_scheduler():
        await chat_service._startup_event()
        try:
            invocation.start()
            if not await asyncio.to_thread(started.wait, 5):
                raise AssertionError("optional inference did not start")
            if cpu_pressure:
                cpu_telemetry["utilization_percent"] = 95.0
            if game_active:
                presence_message = presence_publisher.publish_once(("ExampleGame.exe",))
                game_message_id["value"] = presence_message.payload["message_id"]
                bridge._foreground_game_detector = game_detector
                bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
            else:
                bridge._notify_resource_reconciliation_wakeup()
            assert bridge.resource_reconciliation_interval_seconds() == 0.5
            if not await asyncio.to_thread(cancelled.wait, 5):
                raise AssertionError(
                    f"scheduled resource-priority cancellation was not delivered: "
                    f"{reconciliations!r}")
            if game_active:
                expected_release_trigger = ("idle_game_reconciliation" if cpu_pressure
                    else "idle_game_gpu_residency")
                release_deadline = time.monotonic() + 5
                while time.monotonic() < release_deadline:
                    if any(item.get("trigger_kind") == expected_release_trigger
                            and item.get("status") == "worker_closed"
                            for item in reconciliations):
                        break
                    await asyncio.sleep(.01)
                else:
                    raise AssertionError(
                        f"scheduled game-priority release was not confirmed: "
                        f"{reconciliations!r}")
            await asyncio.to_thread(invocation.join, 5)
            assert not invocation.is_alive()
            runtime_residency["model_closed"] = model.closed
            runtime_residency["session_current"] = (
                serving.current_session() == session)
            return chat_service._RESOURCE_RECONCILIATION_TASK is not None
        finally:
            await chat_service._shutdown_event()

    try:
        scheduler_started = asyncio.run(run_reconciliation_scheduler())
    finally:
        chat_service._PRODUCTION_COMPOSITION = previous_composition
        chat_service._RESOURCE_RECONCILIATION_TASK = previous_reconciliation_task
        resource_custody.close()
        game_detector.close()

    assert scheduler_started is True
    assert not invocation.is_alive()
    if game_active:
        trigger_kind = ("idle_game_reconciliation" if cpu_pressure
            else "idle_game_gpu_residency")
        reconciliation = next((item for item in reconciliations
            if item.get("trigger_kind") == trigger_kind), None)
        assert reconciliation is not None, reconciliations
        assert reconciliation["status"] == "worker_closed", reconciliations
        assert reconciliation["trigger_kind"] == trigger_kind
        if cpu_pressure:
            preemption = next((item for item in reconciliations
                if item.get("trigger_kind") ==
                    "verified_game_workload_active_inference_preemption"), None)
            assert preemption is not None, reconciliations
            assert preemption["active_inference_cancellation_confirmed"] is True
        else:
            assert reconciliation["active_inference_cancellation_confirmed"] is True
    else:
        preemption = next((item for item in reconciliations
            if item.get("trigger_kind") ==
                "host_resource_pressure_active_inference_preemption"), None)
        assert preemption is not None, reconciliations
        assert preemption["status"] == "preempted"
        assert preemption["active_inference_cancellation_confirmed"] is True
    assert invocation_result["receipt"].status == "cancelled"
    assert invocation_result["receipt"].output_text is None
    assert resource_ledger.remaining_calls(bundle.allocation_id) == 1
    assert len(resource_ledger._state["attempts"]) == 1
    assert resource_ledger._state["receipts"][-2]["state"] == "measured_cancelled"
    assert resource_ledger._state["receipts"][-2][
        "resource_specific_measurement"]["invocation_outcome"] == "cancelled"
    assert resource_ledger._state["receipts"][-1]["state"] == "reconciled"
    from sentientos.governed_local_model_resource_allocation import (
        GovernedLocalModelResourceLedger,
    )
    recovered_ledger = GovernedLocalModelResourceLedger(resource_ledger.path)
    assert recovered_ledger.remaining_calls(bundle.allocation_id) == 1
    assert [item["state"] for item in recovered_ledger._state["receipts"][-3:]] == [
        "attempt_begun", "measured_cancelled", "reconciled"]
    assert runtime_residency["model_closed"] is game_active
    assert runtime_residency["session_current"] is (not game_active)

    release_directory = (tmp_path / "state" / "installations" / "install-1" /
        "state" / "local-model" / "serving" / "resource-release-receipts")
    if not game_active:
        assert not list(release_directory.glob("*.json"))
        preemption_decision = next(json.loads(line) for line in reversed(
            (tmp_path / "kernel-decisions.jsonl").read_text(
                encoding="utf-8").splitlines())
            if json.loads(line).get("action_kind") == "local_model_inference_preemption")
        preemption_governor = preemption_decision["delegated_outcomes"]["runtime_governor"]
        assert preemption_governor["allowed"] is True
        assert preemption_governor["reason"] == (
            "allowed_host_resource_pressure_inference_preemption")
        assert preemption_governor["evidence_refs"]["host_resource_evidence"][
            "pressure_labels"] == ["cpu_pressure"]
        return

    release_path = next(release_directory.glob("*.json"))
    release = json.loads(release_path.read_text(encoding="utf-8"))
    assert release["active_inference_preemption_requested"] is (not cpu_pressure)
    assert release["active_inference_cancellation_confirmed"] is (
        None if cpu_pressure else True)
    assert release["resource_observation"]["game_workload_message_id"] == (
        game_message_id["value"])
    if cpu_pressure:
        assert release["resource_observation"]["pressure_labels"] == ["cpu_pressure"]
        assert release["resource_observation"]["host_report_id"]
        assert host_owner.collector_call_count >= 6
    else:
        assert release["resource_observation"]["model_gpu_layers"] == 24
        assert host_owner.collector_call_count >= 6
    assert release["inference_performed"] is False
    assert release["host_mutation_performed"] is False
    release_decision = next(json.loads(line) for line in reversed(
        (tmp_path / "kernel-decisions.jsonl").read_text(
            encoding="utf-8").splitlines())
        if json.loads(line).get("action_kind") == "local_model_resource_release")
    release_governor = release_decision["delegated_outcomes"]["runtime_governor"]
    assert release_governor["allowed"] is True
    assert release_governor["evidence_refs"]["resource_observation_evidence"][
        "active_inference_preemption_requested"] is (not cpu_pressure)
    assert resource_ledger.remaining_calls(bundle.allocation_id) == 1
    assert len(resource_ledger._state["attempts"]) == 1
    assert resource_ledger._state["receipts"][-1]["state"] == "reconciled"
    serving.close()


def test_governed_resource_release_retries_after_worker_close_failure(monkeypatch, tmp_path):
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
    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        gpu_layers=24)
    bridge.set_workload_mode("gaming")
    close_calls = 0

    def close_once_fails():
        nonlocal close_calls
        close_calls += 1
        if close_calls == 1:
            raise RuntimeError("worker_shutdown_unconfirmed")
        model.closed = True

    model.close = close_once_fails
    receipt_root = (tmp_path / "state" / "installations" / "install-1" / "state" /
        "local-model" / "serving" / "resource-release-receipts")

    failed = bridge.reconcile_idle_game_resource_state()

    assert failed["status"] == "release_effect_unconfirmed"
    assert model.closed is False
    assert serving._session == session
    failed_receipt = json.loads(next(receipt_root.glob("*.json")).read_text(
        encoding="utf-8"))
    assert failed_receipt["status"] == "release_effect_unconfirmed"
    assert failed_receipt["close_failure"] == "RuntimeError"

    retried = bridge.reconcile_idle_game_resource_state()

    assert retried["status"] == "worker_closed"
    assert model.closed is True
    assert serving._session is None and serving._model is None
    release_receipts = [json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(receipt_root.glob("*.json"))]
    assert {item["status"] for item in release_receipts} == {
        "release_effect_unconfirmed", "worker_closed"}
    assert sum(item["receipt_id"] == failed_receipt["receipt_id"]
        and item["status"] == "release_effect_unconfirmed"
        for item in release_receipts) == 1
    decisions = [json.loads(line) for line in (tmp_path / "kernel-decisions.jsonl"
        ).read_text(encoding="utf-8").splitlines()]
    release_admissions = [item for item in decisions
        if item.get("action_kind") == "local_model_resource_release"]
    assert len(release_admissions) == 2
    assert all(item["delegated_outcomes"]["runtime_governor"]["allowed"]
        for item in release_admissions)


def test_idle_reconciliation_keeps_serving_session_without_verified_game(monkeypatch, tmp_path):
    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path)
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
    outcome = bridge.reconcile_idle_game_resource_state()
    assert outcome["status"] == "skipped"
    assert outcome["reason"] == "fresh_verified_game_evidence_required"
    assert model.calls == 0 and model.closed is False
    assert serving.current_session() == session


def test_scheduled_reconciliation_restores_released_model_through_fresh_serving_admission(
        monkeypatch, tmp_path):
    admission_contexts = []
    models = []
    restored = threading.Event()
    recovered_results = []

    def admission_context(correlation_id, _activation_state):
        admission_contexts.append(correlation_id)
        return {"resource_governance_required": True,
            "purpose": "local_model_serving",
            "host_resource_observation_id": correlation_id}

    def model_factory_factory(identity, initial_model):
        def create(_config, _load):
            if not models:
                models.append(initial_model)
                return initial_model
            model = Model(identity)
            models.append(model)
            return model
        return create

    _bridge, serving, first_session, _first_model, kernel, _ = setup(
        monkeypatch, tmp_path, serving_admission_context_provider=admission_context,
        model_factory=model_factory_factory)
    assert serving.release_current_session_after_resource_admission(
        first_session, reason="governed_resource_pressure") is True
    assert models[0].closed is True
    assert serving.current_session() is None
    assert serving.resource_recovery_pending() is True

    from sentientos import chat_service
    service = SimpleNamespace(reconcile_workload_state=lambda: {"status": "observed"},
        resource_reconciliation_interval_seconds=lambda: 0.5,
        set_resource_reconciliation_wakeup=lambda _callback: None,
        close_outputs=lambda: None)
    class RecordingComposition(chat_service.ProductionChatComposition):
        def reconcile_workload_state(self):
            result = super().reconcile_workload_state()
            recovered_results.append(result)
            if result.get("serving_recovery", {}).get("status") == "restored":
                restored.set()
            return result

    composition = RecordingComposition(service, serving)
    previous_composition = chat_service._PRODUCTION_COMPOSITION
    previous_task = chat_service._RESOURCE_RECONCILIATION_TASK
    chat_service._PRODUCTION_COMPOSITION = composition
    chat_service._RESOURCE_RECONCILIATION_TASK = None

    async def run_reconciliation_scheduler():
        import asyncio

        await chat_service._startup_event()
        try:
            if not await asyncio.to_thread(restored.wait, 5):
                raise AssertionError("scheduled resource recovery did not restore serving")
            return (recovered_results[-1], serving.current_session(),
                serving.resource_recovery_pending(), models[1].closed)
        finally:
            await chat_service._shutdown_event()

    try:
        import asyncio

        result = asyncio.run(run_reconciliation_scheduler())
    finally:
        chat_service._PRODUCTION_COMPOSITION = previous_composition
        chat_service._RESOURCE_RECONCILIATION_TASK = previous_task

    result, restored_session, recovery_pending, restored_model_closed = result
    assert result["status"] == "observed"
    assert result["serving_recovery"]["status"] == "restored", result["serving_recovery"]
    assert restored_session is not None and restored_session != first_session
    assert restored_session.binding["serving_operation_id"] != first_session.binding["serving_operation_id"]
    assert len(models) == 2 and restored_model_closed is False
    assert len(admission_contexts) == 4 and len(set(admission_contexts)) == 4
    assert [request.authority_class for request in kernel.requests].count(
        AuthorityClass.MODEL_SERVING) == 4
    assert recovery_pending is False
    composition.close()
    serving.close()


@pytest.mark.parametrize("pressure_kind", ["gpu", "memory", "cpu", "thermal"])
def test_scheduled_recovery_waits_for_fresh_host_pressure_to_clear(
        monkeypatch, tmp_path, pressure_kind):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    gpu = {"gpu_utilization_percent": 20.0,
        "vram_utilization_percent": 30.0}
    memory = {"used_percent": 40.0}
    cpu = {"utilization_percent": 20.0}
    thermal = {"zones": [{"id": "cpu", "temperature_c": 55.0,
        "telemetry_only": True, "control_available": False}]}
    serving_mode = {"value": "normal"}
    recovery_game = {"active": False, "sequence": 0, "message_id": None}

    def collector(collector_id, **values):
        def collect(*, observed_at=None):
            current = ({"device_count": 1, "devices": [{"index": 0, **gpu}]}
                if collector_id == "nvidia_gpu" else
                memory if collector_id == "memory" else
                cpu if collector_id == "cpu" else
                thermal if collector_id == "thermal_sensors" else values)
            return HostCollectorResult(collector_id, "available",
                observed_at or now.isoformat(), "synthetic_test_fixture",
                values=dict(current))
        return collect

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu")),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory")),
            HostObservationCollectorSpec("nvidia_gpu", False, ("linux", "unknown"), 3,
                collector("nvidia_gpu")),
            HostObservationCollectorSpec("thermal_sensors", False,
                ("linux", "unknown"), 4, collector("thermal_sensors")),
        ]), clock=lambda: now.isoformat())
    admission_observations = []

    def admission_context(correlation_id, activation_state):
        observation_id = "local-chat-serving-" + hashlib.sha256(
            correlation_id.encode("utf-8")).hexdigest()[:32]
        evaluation = host_owner.run_cycle(correlation_id=observation_id)
        assert evaluation is not None
        from sentientos.host_resource_runtime import validate_evaluation
        assert validate_evaluation(evaluation).ok, validate_evaluation(evaluation).findings
        assert kernel.observe_host_resource_evaluation(evaluation) is True
        admission_observations.append(evaluation.pressure_report.pressure_labels)
        load_configuration = activation_state.get("load_configuration", {})
        gpu_layers = load_configuration.get("n_gpu_layers")
        return {"resource_governance_required": True,
            "purpose": "local_model_serving",
            "host_resource_observation_namespace": "local-chat-serving",
            "host_resource_observation_id": observation_id,
            "model_execution_profile": {
                "schema_version": "sentientos.model_execution_profile:v1",
                "engine": "llama_cpp",
                "accelerator_route": "cpu" if gpu_layers == 0 else "gpu",
                "gpu_layers": gpu_layers,
                "configuration_digest": digest_payload(load_configuration)},
            "workload_mode": serving_mode["value"],
            "effective_workload_mode": (
                "gaming" if recovery_game["active"] else
                "normal" if serving_mode["value"] == "automatic" else serving_mode["value"]),
            "serving_workload_evidence": {
                "configured_mode": serving_mode["value"],
                "mode_source": "operator_selected",
                "observation_status": "available" if serving_mode["value"] == "automatic"
                    else "not_requested",
                "game_foreground": (recovery_game["active"]
                    if serving_mode["value"] == "automatic" else None),
                "game_process_running": (recovery_game["active"]
                    if serving_mode["value"] == "automatic" else None),
                "transport_provenance": ({"message_id": recovery_game["message_id"]}
                    if serving_mode["value"] == "automatic" else None),
            }}

    def publish_recovery_game(active):
        recovery_game["sequence"] += 1
        message_id = hashlib.sha256(
            f"recovery-game-{pressure_kind}-{recovery_game['sequence']}-{active}".encode(
                "utf-8")).hexdigest()
        observation = ForegroundGameObservation(
            "available", active, hashlib.sha256(b"examplegame.exe").hexdigest(),
            now.isoformat(), transport_provenance={
                "message_id": message_id, "source_id": "windows-edge",
                "session_id": "recovery-game-session", "generation_id": "edge-generation",
                "sequence": recovery_game["sequence"],
                "envelope_created_at": now.isoformat()},
            game_process_running=active,
            running_process_name_digests=(
                (hashlib.sha256(b"examplegame.exe").hexdigest(),) if active else ()))
        assert kernel.observe_verified_game_workload(observation)
        recovery_game["active"] = active
        recovery_game["message_id"] = message_id

    models = []

    def model_factory(identity, initial_model):
        def create(_config, _load):
            model = initial_model if not models else Model(identity)
            models.append(model)
            return model
        return create

    bridge, serving, first_session, first_model, _kernel, _ = setup(
        monkeypatch, tmp_path, kernel_override=kernel,
        host_resource_observation_owner=host_owner,
        serving_admission_context_provider=admission_context,
        gpu_layers=24 if pressure_kind == "gpu" else 0,
        model_factory=model_factory)
    if pressure_kind == "gpu":
        gpu.update(gpu_utilization_percent=95.0, vram_utilization_percent=92.0)
    elif pressure_kind == "memory":
        memory.update(used_percent=95.0)
    elif pressure_kind == "cpu":
        cpu.update(utilization_percent=95.0)
    else:
        thermal["zones"][0]["temperature_c"] = 92.0
    if pressure_kind in {"cpu", "thermal"}:
        serving_mode["value"] = "gaming"
        bridge.set_workload_mode("gaming")
    release = bridge.reconcile_idle_game_resource_state()
    assert release["status"] == "worker_closed"
    expected_trigger = {"gpu": "idle_host_gpu_resource_reconciliation",
        "memory": "idle_host_memory_resource_reconciliation",
        "cpu": "gaming_profile_resource_reconciliation",
        "thermal": "gaming_profile_resource_reconciliation"}[pressure_kind]
    assert release["trigger_kind"] == expected_trigger
    assert first_model.closed is True
    assert serving.resource_recovery_pending() is True

    from sentientos import chat_service
    deferred = threading.Event()
    restored = threading.Event()
    recovery_results = []
    wakeup_callbacks = []
    service = SimpleNamespace(reconcile_workload_state=lambda: {"status": "observed"},
        resource_reconciliation_interval_seconds=lambda: 60.0,
        set_resource_reconciliation_wakeup=lambda callback: wakeup_callbacks.append(callback),
        close_outputs=lambda: None)

    class RecordingComposition(chat_service.ProductionChatComposition):
        def reconcile_workload_state(self):
            result = super().reconcile_workload_state()
            recovery_results.append(result)
            status = result.get("serving_recovery", {}).get("status")
            if status == "deferred":
                deferred.set()
            elif status == "restored":
                restored.set()
            return result

    composition = RecordingComposition(service, serving)
    previous_composition = chat_service._PRODUCTION_COMPOSITION
    previous_task = chat_service._RESOURCE_RECONCILIATION_TASK
    chat_service._PRODUCTION_COMPOSITION = composition
    chat_service._RESOURCE_RECONCILIATION_TASK = None

    async def run_reconciliation_scheduler():
        import asyncio

        await chat_service._startup_event()
        try:
            if not await asyncio.to_thread(deferred.wait, 5):
                raise AssertionError("scheduler did not defer recovery under host pressure")
            assert serving.current_session() is None
            assert serving.resource_recovery_pending() is True
            assert len(models) == 1
            gpu.update(gpu_utilization_percent=20.0, vram_utilization_percent=30.0)
            memory.update(used_percent=40.0)
            cpu.update(utilization_percent=20.0)
            thermal["zones"][0]["temperature_c"] = 55.0
            serving_mode["value"] = "automatic"
            publish_recovery_game(True)
            callback = wakeup_callbacks[-1]
            callback()
            game_serving_reason = (
                "deferred_gpu_model_serving_while_game_active"
                if pressure_kind == "gpu" else
                "deferred_cpu_model_serving_while_game_active")
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if (recovery_results and recovery_results[-1].get(
                        "serving_recovery", {}).get("status") == "deferred"
                        and len(models) == 1):
                    decisions_now = [json.loads(line) for line in
                        (tmp_path / "kernel-decisions.jsonl").read_text(
                            encoding="utf-8").splitlines()]
                    if any(item.get("action_kind") ==
                            "establish_exact_activated_model_serving_session"
                            and item.get("delegated_outcomes", {}).get(
                                "runtime_governor", {}).get("reason") ==
                                game_serving_reason
                            for item in decisions_now):
                        break
                await asyncio.sleep(.01)
            else:
                raise AssertionError(
                    "recovery did not defer while the verified game remained active")
            assert serving.current_session() is None
            assert serving.resource_recovery_pending() is True
            publish_recovery_game(False)
            callback()
            if not await asyncio.to_thread(restored.wait, 5):
                raise AssertionError("scheduler did not recover after host pressure cleared")
            decisions = [json.loads(line) for line in
                (tmp_path / "kernel-decisions.jsonl").read_text(
                    encoding="utf-8").splitlines()]
            pressure_reasons = [item.get("delegated_outcomes", {}).get(
                "runtime_governor", {}).get("reason") for item in decisions
                if item.get("action_kind") ==
                    "establish_exact_activated_model_serving_session"]
            return (recovery_results[-1], admission_observations[:], pressure_reasons,
                serving.current_session(), serving.resource_recovery_pending(),
                models[1].closed)
        finally:
            await chat_service._shutdown_event()

    try:
        import asyncio

        outcome = asyncio.run(run_reconciliation_scheduler())
    finally:
        chat_service._PRODUCTION_COMPOSITION = previous_composition
        chat_service._RESOURCE_RECONCILIATION_TASK = previous_task

    (result, observed_labels, pressure_reasons, restored_session, recovery_pending,
        restored_model_closed) = outcome
    assert result["serving_recovery"]["status"] == "restored"
    expected_pressure = {"gpu": "gpu_pressure", "memory": "memory_pressure",
        "cpu": "cpu_pressure", "thermal": "thermal_pressure"}[pressure_kind]
    assert any(expected_pressure in labels for labels in observed_labels)
    assert observed_labels[-1] == ("nominal",)
    expected_deferred_serving_reason = (
        "deferred_local_model_serving_under_host_pressure_in_gaming_mode"
        if pressure_kind in {"cpu", "thermal"} else
        "deferred_background_model_serving_under_memory_pressure"
        if pressure_kind == "memory" else
        "deferred_background_model_serving_under_host_pressure")
    assert expected_deferred_serving_reason in pressure_reasons
    assert restored_session is not None and restored_session != first_session
    assert restored_session.binding["serving_operation_id"] != first_session.binding[
        "serving_operation_id"]
    assert recovery_pending is False
    assert len(models) == 2 and restored_model_closed is False
    assert len(admission_observations) >= 3
    composition.close()
    serving.close()


@pytest.mark.parametrize("gpu_layers,expected_detector_calls", [(0, 2), (24, 3)])
def test_automatic_game_release_revalidates_game_before_release(
        monkeypatch, tmp_path, gpu_layers, expected_detector_calls):
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
        host_resource_observation_owner=host_owner, gpu_layers=gpu_layers)
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])

    result = bridge.reconcile_idle_game_resource_state()

    assert result["status"] == "skipped", (result, detector.calls)
    assert result["reason"] == "fresh_verified_game_evidence_required"
    assert detector.calls == expected_detector_calls
    assert model.closed is False
    assert serving.current_session() == session
    assert list((tmp_path / "state" / "installations" / "install-1" /
        "state" / "local-model" / "serving" /
        "resource-release-receipts").glob("*.json")) == []
    serving.close()


@pytest.mark.parametrize("mode,style_expected", [("normal", False), ("gaming", True)])
def test_gaming_style_is_bound_into_the_exact_serving_prompt(monkeypatch, tmp_path, mode, style_expected):
    from sentientos.gaming_workload_policy import GamingWorkloadPolicy

    bridge, _, _, model, _, _ = setup(monkeypatch, tmp_path)
    bridge.set_workload_mode(mode)
    prompt = ("[SYSTEM_INSTRUCTION]\nBase rules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
              "[SESSION_HISTORY_DATA]\nUSER_DATA: hello")

    receipt = bridge.generate(prompt=prompt, caller="chat_service", correlation_id="gaming-style")

    observed_prompt = model.prompts[0]
    instruction = GamingWorkloadPolicy.GAMING_CHAT_STYLE_INSTRUCTION
    assert (instruction in observed_prompt) is style_expected
    assert receipt.request["linkage"].get("workload_response_style") == (
        GamingWorkloadPolicy.GAMING_CHAT_STYLE_ID if style_expected else None)
    assert receipt.request["linkage"].get("max_backend_threads") == (2 if style_expected else None)
    assert receipt.generation_config["actual_generation_parameters"].get(
        "max_backend_threads") == (2 if style_expected else None)




def test_authenticated_game_evidence_defers_cpu_inference(monkeypatch, tmp_path):
    """Authenticated game presence defers optional CPU inference."""
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding
    from sentientos.foreground_game_detection import ForegroundGameDetector
    from sentientos.gaming_companion_tls_transport import (
        CompanionBridgeMutualTLSClient, CompanionBridgeMutualTLSRuntime,
    )
    from tests.test_gaming_companion_tls_transport import _certificate_bundle
    from sentientos.governed_local_model_invocation import LocalModelInvocationBudget

    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    server_certificate = x509.load_pem_x509_certificate(
        (tmp_path / "server.pem").read_bytes())
    source_key, acknowledgment_key = b"r" * 32, b"s" * 32
    source_id, generation_id = "windows-edge", "gaming-inference-generation-1"
    runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1", port=0,
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=CompanionBridgeReceiver(source_keys={source_id: source_key},
            expected_generations={source_id: generation_id}),
        acknowledgment_source_id="wsl-core",
        acknowledgment_generation_id="gaming-inference-core-generation-1",
        acknowledgment_key=acknowledgment_key)
    port = runtime.start()
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core": acknowledgment_key},
            expected_generations={"wsl-core": "gaming-inference-core-generation-1"}),
        expected_server_certificate_sha256=hashlib.sha256(
            server_certificate.public_bytes(Encoding.DER)).hexdigest())
    publisher = WindowsForegroundBridgePublisher(
        detector=ForegroundGameDetector(system_provider=lambda: "Windows",
            process_name_provider=lambda: "ExampleGame.exe",
            running_process_names_provider=lambda: ("ExampleGame.exe",),
            clock=lambda: now.isoformat()),
        client=client, source_id=source_id,
        session_id="authenticated-gaming-inference-session",
        generation_id=generation_id, source_key=source_key)
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=source_id,
        generation_id=generation_id, clock=lambda: now)
    detector.set_game_workload_admission_owner(kernel)

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
        ]), clock=lambda: now.isoformat())
    bridge, serving, _, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, foreground_game_detector=detector,
        host_resource_observation_owner=host_owner, gpu_layers=0)
    try:
        message = publisher.publish_once(("ExampleGame.exe",))
        bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
        prompt = ("[SYSTEM_INSTRUCTION]\nBase rules.\n[VERIFIED_RUNTIME_CONTEXT]\n{}\n"
            "[SESSION_HISTORY_DATA]\nUSER_DATA: hello")
        receipt = bridge.generate(prompt=prompt, caller="chat_service",
            correlation_id="authenticated-game-constrained-cpu-inference",
            budget=LocalModelInvocationBudget(8000, 4000, 512, 30.0, 2))

        assert receipt.status == "deferred"
        assert model.calls == 0
        lineage = receipt.request["linkage"]["workload_evidence"]
        assert lineage["configured_mode"] == "automatic"
        assert lineage["game_foreground"] is True
        assert lineage["transport_provenance"]["message_id"] == message.payload["message_id"]
        assert receipt.request["linkage"]["workload_mode"] == "gaming"
        assert receipt.request["linkage"]["max_backend_threads"] == 2
        assert host_owner.collector_call_count == 2
        inference_decision = next(json.loads(line) for line in
            (tmp_path / "kernel-decisions.jsonl").read_text(
                encoding="utf-8").splitlines()
            if '"authority_class": "local_model_inference"' in line)
        evidence = inference_decision["delegated_outcomes"][
            "runtime_governor"]["evidence_refs"]["game_workload_evidence"]
        assert evidence["status"] == "current"
        assert evidence["message_id"] == message.payload["message_id"]
        assert inference_decision["delegated_outcomes"][
            "runtime_governor"]["reason"] == (
                "deferred_local_model_inference_while_game_active")
    finally:
        serving.close()
        detector.close()


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


def test_verified_game_presence_preempts_active_cpu_inference_without_pressure(
        monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    message_id = hashlib.sha256(b"authenticated-game-presence").hexdigest()
    game_workload = ForegroundGameObservation("available", True,
        hashlib.sha256(b"examplegame.exe").hexdigest(), now.isoformat(),
        transport_provenance={"message_id": message_id, "source_id": "windows-edge",
            "session_id": "game-session", "generation_id": "edge-generation",
            "sequence": 1, "envelope_created_at": now.isoformat()},
        game_process_running=True,
        running_process_name_digests=(hashlib.sha256(
            b"examplegame.exe").hexdigest(),))
    game_active = threading.Event()

    class VerifiedGameDetector:
        def observe(self, _names):
            if game_active.is_set():
                return game_workload
            return ForegroundGameObservation("available", False, None,
                now.isoformat(), game_process_running=False)

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
        ]), clock=lambda: now.isoformat())
    started = threading.Event()
    cancelled = threading.Event()

    def active_generation():
        started.set()
        if not cancelled.wait(timeout=5):
            raise AssertionError("game workload did not preempt optional CPU inference")
        raise RuntimeError("fixture_cancelled_for_game_workload_priority")

    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        foreground_game_detector=VerifiedGameDetector(), gpu_layers=0,
        on_generate=active_generation)
    model.cancel_pending_generation = lambda: (cancelled.set() or True)
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
    results = {}
    worker = threading.Thread(target=lambda: results.setdefault("receipt",
        bridge.generate(prompt=("[SYSTEM_INSTRUCTION]\nRules.\n"
            "[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\n"
            "USER_DATA: optional inference"), caller="chat_service",
            correlation_id="active-cpu-game-priority")))
    worker.start()
    assert started.wait(timeout=5)

    game_active.set()
    assert kernel.observe_verified_game_workload(game_workload)
    preemption = bridge.reconcile_idle_game_resource_state()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert preemption["status"] == "preempted"
    assert preemption["trigger_kind"] == (
        "verified_game_workload_active_inference_preemption")
    assert preemption["game_workload_message_id"] == message_id
    assert preemption["active_inference_cancellation_confirmed"] is True
    assert results["receipt"].status == "cancelled"
    assert results["receipt"].output_text is None
    assert model.closed is False
    assert serving.current_session() == session
    decisions = [json.loads(line) for line in
        (tmp_path / "kernel-decisions.jsonl").read_text(
            encoding="utf-8").splitlines()]
    decision = next(item for item in decisions
        if item.get("action_kind") == "local_model_inference_preemption")
    assert decision["delegated_outcomes"]["runtime_governor"]["reason"] == (
        "allowed_verified_game_workload_inference_preemption")
    assert host_owner.collector_call_count == 2
    mismatched_workload = bridge.current_workload_state()
    mismatched_workload["transport_provenance"] = {"message_id": "f" * 64}
    rejected = bridge._admit_active_game_inference_preemption(
        session, model, mismatched_workload)
    assert rejected is not None and rejected["status"] == "denied"
    assert model.closed is False
    assert serving.current_session() == session
    serving.close()


def test_verified_game_presence_retries_unconfirmed_cpu_inference_cancellation(
        monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    message_id = hashlib.sha256(b"authenticated-game-presence-retry").hexdigest()
    game_workload = ForegroundGameObservation("available", True,
        hashlib.sha256(b"examplegame.exe").hexdigest(), now.isoformat(),
        transport_provenance={"message_id": message_id, "source_id": "windows-edge",
            "session_id": "game-session", "generation_id": "edge-generation",
            "sequence": 1, "envelope_created_at": now.isoformat()},
        game_process_running=True,
        running_process_name_digests=(hashlib.sha256(
            b"examplegame.exe").hexdigest(),))
    game_active = threading.Event()

    class VerifiedGameDetector:
        def observe(self, _names):
            if game_active.is_set():
                return game_workload
            return ForegroundGameObservation("available", False, None,
                now.isoformat(), game_process_running=False)

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
        ]), clock=lambda: now.isoformat())
    started = threading.Event()
    cancelled = threading.Event()

    def active_generation():
        started.set()
        if not cancelled.wait(timeout=5):
            raise AssertionError("game workload did not retry inference cancellation")
        raise RuntimeError("fixture_cancelled_for_game_workload_priority")

    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        foreground_game_detector=VerifiedGameDetector(), gpu_layers=0,
        on_generate=active_generation)
    cancel_attempt_count = 0

    def cancel_pending_generation():
        nonlocal cancel_attempt_count
        cancel_attempt_count += 1
        if cancel_attempt_count == 1:
            # The backend accepted the request but kept running; the governed
            # owner must report unconfirmed until this invocation exits.
            return True
        cancelled.set()
        return True

    model.cancel_pending_generation = cancel_pending_generation
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
    results = {}
    worker = threading.Thread(target=lambda: results.setdefault("receipt",
        bridge.generate(prompt=("[SYSTEM_INSTRUCTION]\nRules.\n"
            "[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\n"
            "USER_DATA: optional inference"), caller="chat_service",
            correlation_id="active-cpu-game-priority-retry")))
    worker.start()
    assert started.wait(timeout=5)

    game_active.set()
    assert kernel.observe_verified_game_workload(game_workload)
    first = bridge.reconcile_idle_game_resource_state()
    second = bridge.reconcile_idle_game_resource_state()
    worker.join(timeout=5)

    assert first["status"] == "preemption_unconfirmed"
    assert first["active_inference_cancellation_confirmed"] is False
    assert second["status"] == "preempted"
    assert second["game_workload_message_id"] == message_id
    assert second["active_inference_cancellation_confirmed"] is True
    assert cancel_attempt_count == 2
    assert not worker.is_alive()
    assert results["receipt"].status == "cancelled"
    assert serving.current_session() == session
    decisions = [json.loads(line) for line in
        (tmp_path / "kernel-decisions.jsonl").read_text(
            encoding="utf-8").splitlines()]
    preemptions = [item for item in decisions
        if item.get("action_kind") == "local_model_inference_preemption"]
    assert len(preemptions) == 2
    assert all(item["delegated_outcomes"]["runtime_governor"]["reason"] ==
        "allowed_verified_game_workload_inference_preemption"
        for item in preemptions)
    assert host_owner.collector_call_count == 2
    serving.close()


def test_verified_game_presence_defers_each_new_inference_on_same_snapshot(
        monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    message_id = hashlib.sha256(b"stable-authenticated-game-presence").hexdigest()
    game_workload = ForegroundGameObservation("available", True,
        hashlib.sha256(b"examplegame.exe").hexdigest(), now.isoformat(),
        transport_provenance={"message_id": message_id, "source_id": "windows-edge",
            "session_id": "game-session", "generation_id": "edge-generation",
            "sequence": 1, "envelope_created_at": now.isoformat()},
        game_process_running=True,
        running_process_name_digests=(hashlib.sha256(
            b"examplegame.exe").hexdigest(),))
    game_stopped = ForegroundGameObservation("available", False,
        hashlib.sha256(b"explorer.exe").hexdigest(), now.isoformat(),
        transport_provenance={"message_id": hashlib.sha256(
            b"authenticated-game-stopped-sequence-2").hexdigest(),
            "source_id": "windows-edge", "session_id": "game-session",
            "generation_id": "edge-generation", "sequence": 2,
            "envelope_created_at": now.isoformat()},
        game_process_running=False, running_process_name_digests=())
    current_observation = [game_workload]
    last_observed_message_id = [None]

    class VerifiedGameDetector:
        def observe(self, _names):
            observation = current_observation[0]
            provenance = observation.transport_provenance
            message_id = provenance["message_id"] if provenance is not None else None
            if message_id != last_observed_message_id[0]:
                assert kernel.observe_verified_game_workload(observation)
                last_observed_message_id[0] = message_id
            return observation

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
        ]), clock=lambda: now.isoformat())
    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        foreground_game_detector=VerifiedGameDetector(), gpu_layers=0)
    _, _, _, resource_context, resource_ledger = resource_allocation_setup(
        tmp_path / "game-priority-resource-allocation", calls=2,
        max_input_chars=8192)
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
    prompt = ("[SYSTEM_INSTRUCTION]\nRules.\n"
        "[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\n"
        "USER_DATA: optional inference")
    budget = LocalModelInvocationBudget(8192, 200, 20, 5.0, 2)
    receipts = [bridge.generate(prompt=prompt, caller="chat_service",
        correlation_id=correlation_id, budget=budget,
        resource_context=replace(resource_context,
            durable_attempt_nonce=f"{correlation_id}-nonce"))
        for correlation_id in (
            "active-cpu-game-priority-first", "active-cpu-game-priority-second")]
    current_observation[0] = game_stopped
    receipts.append(bridge.generate(prompt=prompt, caller="chat_service",
        correlation_id="inference-after-game-stopped", budget=budget,
        resource_context=replace(resource_context,
            durable_attempt_nonce="inference-after-game-stopped-nonce")))

    assert [receipt.status for receipt in receipts] == [
        "deferred", "deferred", "admitted_completed"]
    assert model.calls == 1
    assert resource_ledger.snapshot_counts() == (1, 1, 3)
    assert resource_ledger.remaining_calls(
        resource_context.allocation.allocation_id) == 1
    assert serving.current_session() == session
    decisions = [json.loads(line) for line in
        (tmp_path / "kernel-decisions.jsonl").read_text(
            encoding="utf-8").splitlines()]
    inference_decisions = [item for item in decisions
        if item.get("action_kind") == "local_model_inference"]
    assert len(inference_decisions) == 3
    assert all(item["delegated_outcomes"]["runtime_governor"]["reason"] ==
        "deferred_local_model_inference_while_game_active"
        for item in inference_decisions[:2])
    assert inference_decisions[2]["delegated_outcomes"]["runtime_governor"][
        "allowed"] is True
    assert all(item["delegated_outcomes"]["runtime_governor"][
        "evidence_refs"]["observed_pressure_labels"] == ["nominal"]
        for item in inference_decisions)
    assert all(item["delegated_outcomes"]["runtime_governor"][
        "evidence_refs"]["game_workload_evidence"]["message_id"] == message_id
        for item in inference_decisions[:2])
    assert inference_decisions[2]["delegated_outcomes"]["runtime_governor"][
        "evidence_refs"]["game_workload_evidence"]["game_active"] is False
    assert host_owner.collector_call_count == 6
    serving.close()


def test_game_priority_retains_timed_out_backend_for_later_preemption(
        monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    message_id = hashlib.sha256(b"authenticated-game-during-timeout").hexdigest()
    game_workload = ForegroundGameObservation("available", True,
        hashlib.sha256(b"examplegame.exe").hexdigest(), now.isoformat(),
        transport_provenance={"message_id": message_id, "source_id": "windows-edge",
            "session_id": "game-session", "generation_id": "edge-generation",
            "sequence": 1, "envelope_created_at": now.isoformat()},
        game_process_running=True,
        running_process_name_digests=(hashlib.sha256(
            b"examplegame.exe").hexdigest(),))
    game_active = threading.Event()

    class VerifiedGameDetector:
        def observe(self, _names):
            if game_active.is_set():
                return game_workload
            return ForegroundGameObservation("available", False, None,
                now.isoformat(), game_process_running=False)

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
        ]), clock=lambda: now.isoformat())
    _, _, _, resource_context, resource_ledger = resource_allocation_setup(
        tmp_path / "resource-allocation", calls=2, max_input_chars=8192)
    started = threading.Event()
    release_worker = threading.Event()

    def active_generation():
        started.set()
        if not release_worker.wait(timeout=5):
            raise AssertionError("lingering inference was not preempted by game priority")
        raise RuntimeError("fixture_stopped_after_game_preemption")

    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        foreground_game_detector=VerifiedGameDetector(), gpu_layers=0,
        on_generate=active_generation)
    admission_inputs = []
    original_preemption_admission = (
        ProductionServingInferenceController._admit_active_game_inference_preemption)

    def capture_preemption_admission(controller, serving_session, inference_model,
            workload):
        admission_inputs.append(dict(workload))
        return original_preemption_admission(
            controller, serving_session, inference_model, workload)

    monkeypatch.setattr(ProductionServingInferenceController,
        "_admit_active_game_inference_preemption", capture_preemption_admission)
    cancellation_attempts = 0

    def cancel_pending_generation():
        nonlocal cancellation_attempts
        cancellation_attempts += 1
        if cancellation_attempts == 1:
            return False
        release_worker.set()
        return True

    model.cancel_pending_generation = cancel_pending_generation
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])

    timed_out = bridge.generate(prompt=("[SYSTEM_INSTRUCTION]\nX\n"
        "[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\nU"),
        caller="chat_service",
        correlation_id="game-priority-timeout-lingering-worker",
        budget=LocalModelInvocationBudget(max_input_chars=8192,
            max_output_chars=200, max_new_tokens=20, timeout_seconds=0.02,
            max_calls_per_correlation=2),
        resource_context=resource_context)

    assert started.is_set(), (timed_out.status, timed_out.reason_codes)
    assert timed_out.status == "timeout"
    assert cancellation_attempts == 1
    assert bridge.resource_reconciliation_interval_seconds() == 0.5
    game_active.set()
    assert kernel.observe_verified_game_workload(game_workload)
    workload_after_timeout = bridge.current_workload_state()
    assert workload_after_timeout["configured_mode"] == "automatic"
    assert workload_after_timeout["observation_status"] == "available"
    assert workload_after_timeout["game_process_running"] is True
    assert isinstance(model.active_identity.to_dict(), Mapping)
    assert bridge._active_invoker is not None
    assert bridge._active_invoker.backend_work_pending()
    lingering_invoker = bridge._active_invoker
    overlapping_attempt = bridge.generate(prompt=("[SYSTEM_INSTRUCTION]\nX\n"
        "[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\nU"),
        caller="chat_service",
        correlation_id="game-priority-no-overlapping-backend",
        budget=LocalModelInvocationBudget(max_input_chars=8192,
            max_output_chars=200, max_new_tokens=20, timeout_seconds=0.02,
            max_calls_per_correlation=2),
        resource_context=replace(resource_context,
            durable_attempt_nonce="nonce-second-request"))
    assert overlapping_attempt.status == "deferred"
    assert bridge._active_invoker is lingering_invoker
    assert model.calls == 1
    assert len(resource_ledger._state["attempts"]) == 1
    assert resource_ledger.remaining_calls(resource_context.allocation.allocation_id) == 1
    assert [item["state"] for item in resource_ledger._state["receipts"]] == [
        "attempt_begun", "measured_timeout", "reconciled"]

    preemption = bridge.reconcile_idle_game_resource_state()

    assert admission_inputs, (preemption, workload_after_timeout)
    assert preemption["status"] == "preempted", preemption
    assert preemption["game_workload_message_id"] == message_id
    assert preemption["active_inference_cancellation_confirmed"] is True
    assert cancellation_attempts == 2
    assert bridge.resource_reconciliation_interval_seconds() == 5.0
    assert serving.current_session() == session
    decisions = [json.loads(line) for line in
        (tmp_path / "kernel-decisions.jsonl").read_text(
            encoding="utf-8").splitlines()]
    decision = next(item for item in decisions
        if item.get("action_kind") == "local_model_inference_preemption")
    assert decision["delegated_outcomes"]["runtime_governor"]["reason"] == (
        "allowed_verified_game_workload_inference_preemption")
    assert len(resource_ledger._state["attempts"]) == 1
    assert resource_ledger.remaining_calls(resource_context.allocation.allocation_id) == 1
    assert host_owner.collector_call_count == 4
    serving.close()


def test_game_priority_scheduler_retries_timed_out_allocated_backend(
        monkeypatch, tmp_path, request):
    import asyncio
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding
    from sentientos import chat_service
    from sentientos.canonical_memory import CanonicalMemoryStore
    from sentientos.conversation_session import ConversationSessionStore
    from tests.test_gaming_companion_tls_transport import _certificate_bundle

    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    server_certificate = x509.load_pem_x509_certificate(
        (tmp_path / "server.pem").read_bytes())
    server_pin = hashlib.sha256(server_certificate.public_bytes(Encoding.DER)).hexdigest()
    source_id, generation_id = "windows-edge", "edge-scheduler-generation"
    source_key = b"authenticated-scheduler-game-source-key"
    ack_key = b"authenticated-scheduler-core-ack-key-32"
    runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1", port=0,
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=CompanionBridgeReceiver(source_keys={source_id: source_key},
            expected_generations={source_id: generation_id}),
        acknowledgment_source_id="wsl-core",
        acknowledgment_generation_id="core-scheduler-generation",
        acknowledgment_key=ack_key)
    port = runtime.start()
    request.addfinalizer(runtime.close)
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core": ack_key},
            expected_generations={"wsl-core": "core-scheduler-generation"}),
        expected_server_certificate_sha256=server_pin)

    class GamePresenceSample:
        def observe(self, process_names):
            assert tuple(name.casefold() for name in process_names) == (
                "examplegame.exe",)
            return ForegroundGameObservation("available", True,
                hashlib.sha256(b"examplegame.exe").hexdigest(), now.isoformat())

    publisher = WindowsForegroundBridgePublisher(detector=GamePresenceSample(),
        client=client, source_id=source_id, session_id="scheduler-game-session",
        generation_id=generation_id, source_key=source_key)
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=source_id,
        generation_id=generation_id, clock=lambda: now)
    detector.set_game_workload_admission_owner(kernel)

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
        ]), clock=lambda: now.isoformat())
    _, _, _, resource_context, resource_ledger = resource_allocation_setup(
        tmp_path / "resource-allocation", calls=2, max_input_chars=8192)
    started = threading.Event()
    release_worker = threading.Event()
    worker_stopped = threading.Event()
    timeout_returned = threading.Event()
    invocation_results = {}
    reconciliations = []

    def active_generation():
        started.set()
        if not release_worker.wait(timeout=5):
            raise AssertionError("scheduler did not stop the timed-out inference")
        worker_stopped.set()
        raise RuntimeError("fixture_generation_stopped_by_scheduled_game_preemption")

    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        foreground_game_detector=detector, gpu_layers=0,
        on_generate=active_generation)
    cancellation_attempts = 0

    def cancel_pending_generation():
        nonlocal cancellation_attempts
        cancellation_attempts += 1
        if cancellation_attempts == 1:
            return False
        release_worker.set()
        return True

    model.cancel_pending_generation = cancel_pending_generation
    bridge.set_workload_mode("normal")

    def invoke_until_timeout():
        invocation_results["receipt"] = bridge.generate(
            prompt=("[SYSTEM_INSTRUCTION]\nX\n"
                "[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\nU"),
            caller="chat_service", correlation_id="scheduled-timeout-game-priority",
            budget=LocalModelInvocationBudget(max_input_chars=8192,
                max_output_chars=200, max_new_tokens=20, timeout_seconds=0.02,
                max_calls_per_correlation=2),
            resource_context=resource_context)
        timeout_returned.set()

    invocation = threading.Thread(target=invoke_until_timeout)
    service = chat_service.PersistentConversationService(
        inference=bridge,
        session_store=ConversationSessionStore(tmp_path / "conversation-sessions"),
        memory_store=CanonicalMemoryStore(tmp_path / "canonical-memory"))
    reconcile_workload_state = service.reconcile_workload_state

    def record_scheduled_reconciliation():
        result = reconcile_workload_state()
        reconciliations.append(result)
        return result

    service.reconcile_workload_state = record_scheduled_reconciliation
    previous_composition = chat_service._PRODUCTION_COMPOSITION
    previous_task = chat_service._RESOURCE_RECONCILIATION_TASK
    chat_service._PRODUCTION_COMPOSITION = chat_service.ProductionChatComposition(
        service, serving)
    chat_service._RESOURCE_RECONCILIATION_TASK = None

    async def run_scheduler():
        await chat_service._startup_event()
        try:
            invocation.start()
            if not await asyncio.to_thread(started.wait, 5):
                raise AssertionError("fixture inference did not start")
            if not await asyncio.to_thread(timeout_returned.wait, 5):
                raise AssertionError("bounded invocation did not return its timeout")
            assert invocation_results["receipt"].status == "timeout"
            assert bridge._active_invoker is not None
            assert bridge._active_invoker.backend_work_pending()

            game_message = publisher.publish_once(("ExampleGame.exe",))
            invocation_results["game_message"] = game_message
            bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
            if not await asyncio.to_thread(worker_stopped.wait, 5):
                raise AssertionError("scheduled retry did not stop the backend worker")
            await asyncio.to_thread(invocation.join, 5)
            assert not invocation.is_alive()
            return chat_service._RESOURCE_RECONCILIATION_TASK is not None
        finally:
            await chat_service._shutdown_event()

    try:
        scheduler_started = asyncio.run(run_scheduler())
    finally:
        chat_service._PRODUCTION_COMPOSITION = previous_composition
        chat_service._RESOURCE_RECONCILIATION_TASK = previous_task
        if invocation.is_alive():
            release_worker.set()
            invocation.join(timeout=5)
        serving.close()

    assert scheduler_started is True
    assert reconciliations
    preemption = next(item for item in reconciliations
        if item.get("status") == "preempted")
    assert preemption["game_workload_message_id"] == (
        invocation_results["game_message"].payload["message_id"])
    assert preemption["active_inference_cancellation_confirmed"] is True
    assert cancellation_attempts == 2
    assert model.calls == 1
    assert len(resource_ledger._state["attempts"]) == 1
    assert resource_ledger.remaining_calls(resource_context.allocation.allocation_id) == 1
    assert [item["state"] for item in resource_ledger._state["receipts"]] == [
        "attempt_begun", "measured_timeout", "reconciled"]
    decisions = [json.loads(line) for line in
        (tmp_path / "kernel-decisions.jsonl").read_text(
            encoding="utf-8").splitlines()]
    decision = next(item for item in decisions
        if item.get("action_kind") == "local_model_inference_preemption")
    assert decision["delegated_outcomes"]["runtime_governor"]["reason"] == (
        "allowed_verified_game_workload_inference_preemption")


def test_game_arriving_after_inference_admission_defers_before_backend_entry(
        monkeypatch, tmp_path, request):
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding
    from sentientos.governed_local_model_invocation import LocalModelInvocationBudget
    from tests.test_gaming_companion_tls_transport import _certificate_bundle

    now = datetime.now(timezone.utc)
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_MODE", "enforce")
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path))
    kernel = ControlPlaneKernel(runtime_governor=RuntimeGovernor(),
        decisions_path=tmp_path / "kernel-decisions.jsonl")
    server_context, client_context, peer_digest = _certificate_bundle(tmp_path)
    server_certificate = x509.load_pem_x509_certificate(
        (tmp_path / "server.pem").read_bytes())
    server_pin = hashlib.sha256(server_certificate.public_bytes(Encoding.DER)).hexdigest()
    source_id, generation_id = "windows-edge", "edge-pre-effect-generation"
    source_key = b"authenticated-pre-effect-game-source-key"
    ack_key = b"authenticated-pre-effect-core-ack-key-32"
    runtime = CompanionBridgeMutualTLSRuntime(bind_address="127.0.0.1", port=0,
        tls_context=server_context, expected_peer_certificate_sha256=peer_digest,
        receiver=CompanionBridgeReceiver(source_keys={source_id: source_key},
            expected_generations={source_id: generation_id}),
        acknowledgment_source_id="wsl-core",
        acknowledgment_generation_id="core-pre-effect-generation",
        acknowledgment_key=ack_key)
    port = runtime.start()
    request.addfinalizer(runtime.close)
    client = CompanionBridgeMutualTLSClient(address="127.0.0.1", port=port,
        server_hostname="127.0.0.1", tls_context=client_context,
        acknowledgment_receiver=CompanionBridgeReceiver(
            source_keys={"wsl-core": ack_key},
            expected_generations={"wsl-core": "core-pre-effect-generation"}),
        expected_server_certificate_sha256=server_pin)
    game_active = [False]

    class GamePresenceSample:
        def observe(self, process_names):
            assert tuple(name.casefold() for name in process_names) == (
                "examplegame.exe",)
            return ForegroundGameObservation("available", game_active[0],
                hashlib.sha256((b"examplegame.exe" if game_active[0]
                    else b"explorer.exe")).hexdigest(), now.isoformat(),
                game_process_running=game_active[0],
                running_process_name_digests=(
                    (hashlib.sha256(b"examplegame.exe").hexdigest(),)
                    if game_active[0] else ()))

    publisher = WindowsForegroundBridgePublisher(detector=GamePresenceSample(),
        client=client, source_id=source_id, session_id="pre-effect-game-session",
        generation_id=generation_id, source_key=source_key)
    publisher.publish_once(("ExampleGame.exe",))
    detector = BridgeForegroundGameDetector(runtime=runtime, source_id=source_id,
        generation_id=generation_id, clock=lambda: now)
    detector.set_game_workload_admission_owner(kernel)

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)

    host_owner = HostResourceRuntimeCoordinator(kernel=kernel,
        runtime_state_root=tmp_path / "host-resource",
        plan=build_observation_plan(specs=[
            HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
                collector("cpu", utilization_percent=20.0)),
            HostObservationCollectorSpec("memory", True, ("linux", "unknown"), 2,
                collector("memory", used_percent=40.0)),
        ]), clock=lambda: now.isoformat())
    _, _, _, resource_context, resource_ledger = resource_allocation_setup(
        tmp_path / "resource-allocation", calls=2, max_input_chars=8192)
    bridge, serving, session, model, _, _ = setup(monkeypatch, tmp_path,
        kernel_override=kernel, host_resource_observation_owner=host_owner,
        foreground_game_detector=detector)
    bridge.set_workload_mode("automatic", ["ExampleGame.exe"])
    assert bridge.current_workload_state()["effective_mode"] == "normal"
    original_final_gate = resource_context.allocator.final_gate
    published_game_messages = []

    def publish_game_after_allocation_gate(**kwargs):
        attempt_id = original_final_gate(**kwargs)
        game_active[0] = True
        published_game_messages.append(
            publisher.publish_once(("ExampleGame.exe",)))
        return attempt_id

    monkeypatch.setattr(resource_context.allocator, "final_gate",
        publish_game_after_allocation_gate)
    try:
        receipt = bridge.generate(
            prompt=("[SYSTEM_INSTRUCTION]\nX\n"
                "[VERIFIED_RUNTIME_CONTEXT]\n{}\n[SESSION_HISTORY_DATA]\nU"),
            caller="chat_service", correlation_id="game-arrived-before-backend-entry",
            budget=LocalModelInvocationBudget(max_input_chars=8192,
                max_output_chars=200, max_new_tokens=20, timeout_seconds=1.0,
                max_calls_per_correlation=2),
            resource_context=resource_context)
    finally:
        session_preserved = serving.current_session() == session
        observed_workload = bridge.current_workload_state()
        serving.close()

    assert receipt.status == "deferred"
    game_message_id = published_game_messages[0].payload["message_id"]
    assert ("verified_game_workload_arrived_before_backend_entry:"
        + game_message_id) in receipt.reason_codes
    assert receipt.effects["local_model_inference"] is False
    assert model.calls == 0
    assert session_preserved is True
    assert published_game_messages
    assert host_owner.collector_call_count == 2
    assert resource_ledger.remaining_calls(resource_context.allocation.allocation_id) == 2
    assert [item["state"] for item in resource_ledger._state["receipts"]] == [
        "attempted_not_begun"]
    decisions = [json.loads(line) for line in
        (tmp_path / "kernel-decisions.jsonl").read_text(
            encoding="utf-8").splitlines()]
    inference_decision = next(item for item in decisions
        if item.get("action_kind") == "local_model_inference")
    assert inference_decision["outcome"] == "allow"
    assert observed_workload["game_foreground"] is True
    assert observed_workload["transport_provenance"]["message_id"] == (
        published_game_messages[0].payload["message_id"])


@pytest.mark.parametrize("trigger", ["deferred_inference", "idle_game_reconciliation",
    "idle_nominal_pressure", "idle_cpu_pressure", "deferred_cpu_pressure",
    "idle_game_gpu_residency", "deferred_thermal_pressure",
    "deferred_gpu_thermal_pressure",
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
    late_game_transition = trigger in {
        "idle_game_frame_pressure_active_inference",
        "idle_game_frame_pressure_active_inference_unconfirmed",
        "idle_game_frame_pressure_active_inference_scheduler",
    }
    if not late_game_transition:
        assert kernel.observe_verified_game_performance(game_evidence)
    game_workload_digest = hashlib.sha256(("othergame.exe"
        if trigger == "idle_game_frame_pressure_mismatched_process"
        else "examplegame.exe").encode("utf-8")).hexdigest()
    game_workload = ForegroundGameObservation("available", True, game_workload_digest,
        now.isoformat(), transport_provenance={"message_id": "e" * 64,
            "source_id": "windows-foreground", "session_id": "foreground-session",
            "generation_id": "foreground-generation-1", "sequence": 1,
            "envelope_created_at": now.isoformat()})
    game_workload_active = threading.Event()
    if not late_game_transition:
        assert kernel.observe_verified_game_workload(game_workload)
        game_workload_active.set()

    class VerifiedGameDetector:
        def observe(self, process_names):
            del process_names
            if game_workload_active.is_set():
                return game_workload
            return ForegroundGameObservation("available", False, None,
                now.isoformat(), game_process_running=False)

    def collector(collector_id, **values):
        return lambda *, observed_at=None: HostCollectorResult(
            collector_id, "available", observed_at or now.isoformat(),
            "synthetic_test_fixture", values=values)
    gpu_metrics = ({"gpu": 22.0, "vram": 47.0}
        if trigger in {"idle_nominal_pressure", "idle_cpu_pressure", "deferred_cpu_pressure",
            "idle_game_gpu_residency", "deferred_thermal_pressure",
            "deferred_gpu_thermal_pressure",
            "idle_game_frame_pressure", "idle_game_frame_pressure_mismatched_process",
            "idle_game_frame_pressure_active_inference",
            "idle_game_frame_pressure_active_inference_unconfirmed",
            "idle_game_frame_pressure_active_inference_scheduler"}
        else {"gpu": 94.0, "vram": 91.0})
    cpu_utilization = 95.0 if trigger in {
        "idle_cpu_pressure", "deferred_cpu_pressure"} else 20.0
    cpu_metrics = {"value": cpu_utilization}

    def collect_cpu(*, observed_at=None):
        return HostCollectorResult("cpu", "available",
            observed_at or now.isoformat(), "synthetic_test_fixture",
            values={"utilization_percent": cpu_metrics["value"]})

    def collect_gpu(*, observed_at=None):
        values = {"device_count": 1, "devices": [{"index": 0,
            "gpu_utilization_percent": gpu_metrics["gpu"],
            "vram_utilization_percent": gpu_metrics["vram"]}]}
        if trigger == "deferred_gpu_thermal_pressure":
            values["devices"][0]["temperature_c"] = 92.0
        return HostCollectorResult("nvidia_gpu", "available",
            observed_at or now.isoformat(), "synthetic_test_fixture", values=values)

    def collect_thermal(*, observed_at=None):
        if trigger == "deferred_gpu_thermal_pressure":
            return HostCollectorResult("thermal_sensors", "unavailable",
                observed_at or now.isoformat(), "synthetic_test_fixture",
                warnings=("sensor_unavailable:thermal",))
        return HostCollectorResult("thermal_sensors", "available",
            observed_at or now.isoformat(), "synthetic_test_fixture",
            values={"zones": [{"id": "cpu", "temperature_c":
                92.0 if trigger == "deferred_thermal_pressure" else 55.0,
                "telemetry_only": True, "control_available": False}]})

    host_plan = build_observation_plan(specs=[
        HostObservationCollectorSpec("cpu", True, ("linux", "unknown"), 1,
            collect_cpu),
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
        if trigger in {"idle_cpu_pressure", "deferred_cpu_pressure"}:
            cpu_metrics["value"] = 35.0
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

    if trigger in {"deferred_inference", "deferred_cpu_pressure", "deferred_thermal_pressure",
            "deferred_gpu_thermal_pressure"}:
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
            "deferred_gpu_thermal_pressure": ["sensor_unavailable",
                "thermal_pressure"],
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
            game_workload_active.set()
            assert kernel.observe_verified_game_workload(game_workload)

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
                    game_workload_active.set()
                    assert kernel.observe_verified_game_workload(game_workload)
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
                invocation_receipt = invocation_results["receipt"]
                resource_receipts = resource_ledger._state["receipts"][-3:]
                assert [item["state"] for item in resource_receipts] == [
                    "attempt_begun", "measured_completed", "reconciled"]
                assert resource_receipts[-1]["effect_receipt_digest"] == (
                    invocation_receipt.receipt_digest)
                assert invocation_receipt.resource_allocation_digest == (
                    resource_custody.allocation.allocation_digest)
                assert invocation_receipt.resource_attempt_id == resource_receipts[0][
                    "attempt_id"]
                assert invocation_receipt.resource_consumption_receipt_digests == tuple(
                    item["receipt_digest"] for item in resource_receipts[-2:])
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
    if trigger in {"deferred_inference", "deferred_cpu_pressure", "deferred_thermal_pressure",
            "deferred_gpu_thermal_pressure"}:
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
    observed_collector_calls = host_resource_owner.collector_call_count
    if trigger == "idle_game_frame_pressure_active_inference_scheduler":
        # The scheduler can finish its initial idle tick before game pressure
        # arrives, or begin after the wakeup and take the fast preemption path.
        # Both paths perform the inference sample and post-release sample;
        # only the former adds the optional idle-tick observation.
        assert observed_collector_calls in {8, 12}
    else:
        expected_collector_count = (4 if trigger in {"idle_game_gpu_residency",
            "idle_game_frame_pressure_mismatched_process",
            "idle_game_frame_pressure_active_inference_unconfirmed"} else 8)
        assert observed_collector_calls == expected_collector_count
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
        assert comparison["cpu_utilization_delta_percentage_points"] is None
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
        assert comparison["before"]["cpu_utilization_percent"] == 20.0
        assert comparison["after"]["cpu_utilization_percent"] == 20.0
        assert comparison["cpu_utilization_delta_percentage_points"] == 0.0
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
            "deferred_thermal_pressure", "deferred_gpu_thermal_pressure"}
        else "idle_game_reconciliation")
    assert release["resource_observation"]["game_workload_message_id"] == "e" * 64
    expected_release_pressure = {"idle_cpu_pressure": ["cpu_pressure"],
        "deferred_cpu_pressure": ["cpu_pressure"],
        "deferred_thermal_pressure": ["thermal_pressure"],
        "deferred_gpu_thermal_pressure": ["sensor_unavailable",
            "thermal_pressure"]}
    assert release["resource_observation"]["pressure_labels"] == (
        expected_release_pressure.get(trigger, ["gpu_pressure"]))
    assert release["resource_observation"]["cpu_utilization_percent"] == cpu_utilization
    if trigger == "deferred_gpu_thermal_pressure":
        assert release["resource_observation"]["host_report_id"] == (
            host_reference["report_id"])
        assert release["resource_observation"]["host_report_digest"] == (
            host_reference["report_digest"])
        assert host_reference["thermal_zone_temperatures_c"] == {
            "nvidia_gpu_0": 92.0}
        assert release["resource_observation"]["thermal_zone_temperatures_c"] == {
            "nvidia_gpu_0": 92.0}
    comparison = release["resource_measurement_comparison"]
    assert comparison["status"] == "comparable"
    assert comparison["before"]["gpu_telemetry_sources"] == [{
        "collector_id": "nvidia_gpu", "status": "available",
        "source": "synthetic_test_fixture"}]
    expected_delta = (0.0 if trigger in {"idle_cpu_pressure", "deferred_cpu_pressure",
            "deferred_thermal_pressure", "deferred_gpu_thermal_pressure"}
        else -72.0)
    expected_vram_delta = (0.0 if trigger in {"idle_cpu_pressure", "deferred_cpu_pressure",
            "deferred_thermal_pressure", "deferred_gpu_thermal_pressure"}
        else -44.0)
    assert comparison["gpu_utilization_delta_percentage_points"] == expected_delta
    assert comparison["vram_utilization_delta_percentage_points"] == expected_vram_delta
    expected_cpu_delta = (-60.0 if trigger in {
        "idle_cpu_pressure", "deferred_cpu_pressure"} else 0.0)
    assert comparison["before"]["cpu_utilization_percent"] == cpu_utilization
    assert comparison["after"]["cpu_utilization_percent"] == (
        35.0 if expected_cpu_delta else cpu_utilization)
    assert comparison["cpu_utilization_delta_percentage_points"] == expected_cpu_delta
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
