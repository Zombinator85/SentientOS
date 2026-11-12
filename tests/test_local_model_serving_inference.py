from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
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
    "idle_game_gpu_residency", "deferred_thermal_pressure"])
def test_verified_game_resource_governance_defers_or_releases_before_effect(
        monkeypatch, tmp_path, trigger):
    now = datetime.now(timezone.utc)
    source_id, generation_id = "windows-edge", "windows-edge-generation-1"
    source_key = b"windows-game-pressure-source-key-32"
    verifier = CompanionBridgeReceiver(source_keys={source_id: source_key},
        expected_generations={source_id: generation_id})
    accepted = []
    observer = WindowsGamePerformanceObserver(
        system_provider=lambda: "Windows",
        process_provider=lambda _pid: {"cpu_percent": 12.0, "rss_bytes": 4096},
        frame_provider=lambda _pid: ((), None),
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
        def receive(self, timeout=None):
            del timeout
            return accepted[0]

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
    game_workload = ForegroundGameObservation("available", True, "d" * 64,
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
            "idle_game_gpu_residency", "deferred_thermal_pressure"}
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
    bridge, serving, _, model, _, _ = setup(
        monkeypatch, tmp_path, kernel_override=kernel,
        host_resource_observation_owner=host_resource_owner,
        foreground_game_detector=VerifiedGameDetector(),
        gpu_layers=24 if trigger == "idle_game_gpu_residency" else 0)
    original_close = model.close

    def simulated_release() -> None:
        original_close()
        gpu_metrics.update(gpu=22.0, vram=47.0)

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
    else:
        reconciliation = bridge.reconcile_idle_game_resource_state()
        if trigger == "idle_game_gpu_residency":
            assert reconciliation["status"] == "worker_closed"
            assert reconciliation["trigger_kind"] == "idle_game_gpu_residency"
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
        if trigger != "idle_game_gpu_residency":
            assert reconciliation["status"] == "worker_closed"
            assert isinstance(reconciliation["release_receipt_id"], str)
            assert reconciliation["trigger_kind"] == "idle_game_reconciliation"
            assert reconciliation["observation_correlation_id"].startswith(
                "local-chat-reconciliation-")

    assert model.calls == 0
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
    assert host_resource_owner.collector_call_count == 8
    assert model.closed is True
    assert serving.current_session() is None
    release_receipts = list((tmp_path / "state" / "installations" / "install-1" /
        "state" / "local-model" / "serving" /
        "resource-release-receipts").glob("*.json"))
    assert len(release_receipts) == 1
    release = json.loads(release_receipts[0].read_text(encoding="utf-8"))
    assert release["status"] == "worker_closed"
    if trigger == "idle_game_gpu_residency":
        assert release["trigger_kind"] == "idle_game_gpu_residency"
        assert release["resource_observation"]["game_workload_message_id"] == "e" * 64
        assert release["resource_observation"]["model_gpu_layers"] == 24
        assert release["resource_observation"]["host_telemetry_used_for_admission"] is False
        comparison = release["resource_measurement_comparison"]
        assert comparison["before"]["gpu_utilization_percent"] == 22.0
        assert comparison["after"]["gpu_utilization_percent"] == 22.0
        assert comparison["before"]["vram_utilization_percent"] == 47.0
        assert comparison["after"]["vram_utilization_percent"] == 47.0
        assert comparison["gpu_utilization_delta_percentage_points"] == 0.0
        assert comparison["vram_utilization_delta_percentage_points"] == 0.0
        assert comparison["interpretation"] == (
            "sample_delta_only; telemetry_does_not_establish_causation")
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
