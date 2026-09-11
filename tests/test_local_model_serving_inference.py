from __future__ import annotations

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
    def __init__(self, identity, on_generate=None):
        self.active_identity, self.calls, self.closed, self.on_generate = identity, 0, False, on_generate

    def generate(self, prompt, **kwargs):
        self.calls += 1
        if self.on_generate: self.on_generate()
        return "answer"

    def close(self): self.closed = True


def setup(monkeypatch, tmp_path, *, inference=AdmissionOutcome.ALLOW, on_generate=None):
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
    state = {"installation_identity": "install-1", "generation": 1, "model_id": "catalog-model",
        "artifact_id": "artifact-1", "artifact_path": str(artifact), "artifact_sha256": record.model_content_sha256,
        "artifact_size_bytes": record.artifact_size_bytes, "route_id": "route-1", "runtime_id": "runtime-1",
        "interpreter_path": "/runtime/python", "load_configuration": load,
        "authority_map_digest": authority.map_digest, "commissioning_receipt_id": "commissioning-1",
        "commissioning_receipt_semantic_digest": "commissioning-digest"}
    state["state_semantic_digest"] = semantic_digest(state)
    evidence = {"active_state": state, "activation_receipt": {"receipt_id": "activation-1",
        "receipt_semantic_digest": "activation-digest", "resulting_state_digest": state["state_semantic_digest"]},
        "catalog_proof": {"proof_semantic_digest": "proof-digest"}}
    current = [evidence]
    monkeypatch.setattr("sentientos.local_model_production_serving.verify_current_activation", lambda *a, **k: current[0])
    handle = InstallationStateRegistry(tmp_path / "state", _test_only=True).open(InstallationIdentity.parse("install-1"), create=True)
    kernel, model = Kernel(inference), Model(identity, on_generate)
    serving = ProductionServingController(handle, kernel, model_factory=lambda c, l: model)
    monkeypatch.setattr(serving, "_commissioning_identity", lambda s: identity.to_dict())
    session = serving.establish(operation_id="serve-1")
    return ProductionServingInferenceController(serving), serving, session, model, kernel, current


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
