from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from types import MappingProxyType, SimpleNamespace

import pytest

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass
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
from sentientos.local_model_resource_profile import (
    LLAMA_CPP_RESOURCE_PROFILE_SCHEMA,
    llama_cpp_resource_profile_digest,
)
from sentientos.local_runtime_provisioning import semantic_digest

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

    def generate(self, prompt, **kwargs):
        self.calls += 1
        self.prompts.append(prompt)
        if self.on_generate: self.on_generate()
        return "answer"

    def close(self): self.closed = True


def setup(monkeypatch, tmp_path, *, inference=AdmissionOutcome.ALLOW, on_generate=None,
          installation_identity="install-1", runtime_handoff_id=None, state_root=None,
          serving_operation_id="serve-1", foreground_game_detector=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    artifact = tmp_path / "exact.gguf"; artifact.write_bytes(b"tiny-model")
    load = {"n_ctx": 512, "n_gpu_layers": 0}
    config = ModelConfig([ModelCandidate(artifact, "llama_cpp", "catalog-model", {"gpu_layers": 0})],
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
    kernel, model = Kernel(inference), Model(identity, on_generate)
    serving = ProductionServingController(handle, kernel, model_factory=lambda c, l: model)
    monkeypatch.setattr(serving, "_commissioning_identity", lambda s: identity.to_dict())
    session = serving.establish(operation_id=serving_operation_id)
    return ProductionServingInferenceController(
        serving, runtime_handoff_id=runtime_handoff_id,
        foreground_game_detector=foreground_game_detector), serving, session, model, kernel, current


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


@pytest.mark.parametrize("mode,style_expected", [("normal", False), ("gaming", True)])
def test_gaming_style_is_bound_into_the_exact_serving_prompt(monkeypatch, tmp_path, mode, style_expected):
    bridge, _, _, model, _, _ = setup(monkeypatch, tmp_path)
    bridge.set_workload_mode(mode)
    prompt = "[SYSTEM_INSTRUCTION]\nBase rules.\n[SESSION_HISTORY_DATA]\nUSER_DATA: hello"

    receipt = bridge.generate(prompt=prompt, caller="chat_service", correlation_id="gaming-style")

    observed_prompt = model.prompts[0]
    instruction = "The user is in a gaming workload."
    assert (instruction in observed_prompt) is style_expected
    assert receipt.request["linkage"].get("workload_response_style") == (
        "gaming_chat_style_v1" if style_expected else None)
    assert receipt.request["linkage"].get("max_backend_threads") == (2 if style_expected else None)
    assert receipt.generation_config["actual_generation_parameters"].get(
        "max_backend_threads") == (2 if style_expected else None)


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
            return SimpleNamespace(to_dict=lambda: {"status": "released"})

    invoker = Invoker()
    inference = DevelopmentLocalChatInference(invoker)
    inference.set_workload_mode("gaming")
    assert invoker.release_calls == 1
    assert inference.current_workload_state()["residency_release"] == {
        "status": "released"}
    prompt = "[SYSTEM_INSTRUCTION]\nRules.\n[SESSION_HISTORY_DATA]\nUSER_DATA: hello"
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
        prompt = "[SYSTEM_INSTRUCTION]\nRules.\n[SESSION_HISTORY_DATA]\nUSER_DATA: hello"
        receipt = bridge.generate(prompt=prompt, caller="chat_service", correlation_id="bridged-game")

        assert receipt.status == "admitted_completed"
        assert receipt.generation_config["max_new_tokens"] <= 96
        assert "The user is in a gaming workload." in model.prompts[0]
        linkage = receipt.request["linkage"]
        assert linkage["workload_mode"] == "gaming"
        assert linkage["max_backend_threads"] == 2
        assert receipt.generation_config["actual_generation_parameters"][
            "max_backend_threads"] == 2
        evidence = linkage["workload_evidence"]
        assert evidence["mode_source"] == "foreground_allowlist_match"
        assert evidence["transport_provenance"]["source_id"] == source_id
        assert evidence["transport_provenance"]["generation_id"] == source_generation
        assert evidence["transport_provenance"]["sequence"] == 1
        assert evidence["transport_provenance"]["message_id"]
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
