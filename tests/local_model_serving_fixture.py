"""Reusable serving fixture without a dependency on the pytest runtime."""
from __future__ import annotations

from types import SimpleNamespace

from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_model_authority import build_local_model_authority_map
from sentientos.local_model_production_serving import ProductionServingController
from sentientos.local_model_serving_inference import ProductionServingInferenceController
from sentientos.local_runtime_provisioning import semantic_digest


class FixturePatch:
    """Small reversible patch helper for the isolated child-process fixture."""

    def __init__(self) -> None:
        self._changes: list[tuple[object, str, object]] = []

    def setattr(self, target: object, name: str, value: object | None = None) -> None:
        if value is None:
            module_name, attribute = str(target).rsplit(".", 1)
            target = __import__(module_name, fromlist=[attribute])
            name, value = attribute, name
        previous = getattr(target, name)
        self._changes.append((target, name, previous))
        setattr(target, name, value)

    def undo(self) -> None:
        for target, name, value in reversed(self._changes):
            setattr(target, name, value)
        self._changes.clear()


class Kernel:
    def __init__(self, inference: AdmissionOutcome = AdmissionOutcome.ALLOW) -> None:
        self.inference, self.requests = inference, []

    def admit(self, request: object) -> object:
        self.requests.append(request)
        authority_class = request.authority_class
        outcome = self.inference if authority_class is AuthorityClass.LOCAL_MODEL_INFERENCE else AdmissionOutcome.ALLOW
        return SimpleNamespace(
            outcome=outcome,
            allowed=outcome is AdmissionOutcome.ALLOW,
            authority_class=authority_class,
            actor=request.actor,
            action_kind=request.action_kind,
            target_subsystem=request.target_subsystem,
            correlation_id=request.metadata["correlation_id"],
            reason_codes=("test_denial",) if outcome is not AdmissionOutcome.ALLOW else (),
            admission_decision_ref=f"{authority_class.value}:{request.metadata['correlation_id']}",
            to_dict=lambda: {"outcome": outcome.value},
        )


class Model:
    def __init__(self, identity: object, on_generate: object = None) -> None:
        self.active_identity, self.calls, self.closed, self.on_generate = identity, 0, False, on_generate

    def generate(self, prompt: str, **kwargs: object) -> str:
        self.calls += 1
        if self.on_generate:
            self.on_generate()
        return "answer"

    def close(self) -> None:
        self.closed = True


def setup(monkeypatch: object, tmp_path: object, *, inference: AdmissionOutcome = AdmissionOutcome.ALLOW,
          on_generate: object = None, installation_identity: str = "install-1",
          runtime_handoff_id: str | None = None, state_root: object = None,
          serving_operation_id: str = "serve-1") -> tuple[object, ...]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    artifact = tmp_path / "exact.gguf"
    artifact.write_bytes(b"tiny-model")
    load = {"n_ctx": 512, "n_gpu_layers": 0}
    config = ModelConfig(
        [ModelCandidate(artifact, "llama_cpp", "catalog-model", {"gpu_layers": 0})],
        default_engine="llama_cpp",
        max_context_tokens=512,
        generation=GenerationConfig(max_new_tokens=8, temperature=0, top_p=1),
    )
    authority = build_local_model_authority_map(
        config, allowed_roots=[tmp_path], observed_at="1970-01-01T00:00:00+00:00")
    record = authority.records[0]
    identity = ActiveModelIdentity(
        engine=record.engine,
        resolved_artifact_path=str(artifact.resolve()),
        semantic_artifact_identity=record.semantic_artifact_identity,
        model_content_sha256=record.model_content_sha256,
        artifact_size_bytes=record.artifact_size_bytes,
        sidecar_metadata_digest=record.sidecar_metadata_digest,
        configuration_digest=record.configuration_digest,
        candidate_index=0,
        posture="production",
        fallback=False,
    )
    state = {
        "installation_identity": installation_identity,
        "generation": 1,
        "model_id": "catalog-model",
        "artifact_id": "artifact-1",
        "artifact_path": str(artifact),
        "artifact_sha256": record.model_content_sha256,
        "artifact_size_bytes": record.artifact_size_bytes,
        "route_id": "route-1",
        "runtime_id": "runtime-1",
        "interpreter_path": "/runtime/python",
        "load_configuration": load,
        "authority_map_digest": authority.map_digest,
        "commissioning_receipt_id": "commissioning-1",
        "commissioning_receipt_semantic_digest": "commissioning-digest",
    }
    state["state_semantic_digest"] = semantic_digest(state)
    evidence = {
        "active_state": state,
        "activation_receipt": {
            "receipt_id": "activation-1",
            "receipt_semantic_digest": "activation-digest",
            "resulting_state_digest": state["state_semantic_digest"],
            "expected_prior_activation_state": "ABSENT",
            "observed_prior_activation_state": "ABSENT",
        },
        "activation_history": [{"receipt_id": "activation-1"}],
        "catalog_proof": {"proof_semantic_digest": "proof-digest"},
    }
    current = [evidence]
    monkeypatch.setattr(
        "sentientos.local_model_production_serving.verify_current_activation",
        lambda *args, **kwargs: current[0],
    )
    handle = InstallationStateRegistry(
        state_root or (tmp_path / "state"), _test_only=True).open(
            InstallationIdentity.parse(installation_identity), create=True)
    kernel, model = Kernel(inference), Model(identity, on_generate)
    serving = ProductionServingController(handle, kernel, model_factory=lambda config, load: model)
    monkeypatch.setattr(serving, "_commissioning_identity", lambda state: identity.to_dict())
    session = serving.establish(operation_id=serving_operation_id)
    return (
        ProductionServingInferenceController(serving, runtime_handoff_id=runtime_handoff_id),
        serving,
        session,
        model,
        kernel,
        current,
    )
