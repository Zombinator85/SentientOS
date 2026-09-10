from __future__ import annotations

from types import SimpleNamespace

import pytest

from sentientos.control_plane_kernel import AdmissionOutcome, AuthorityClass
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.local_model import ActiveModelIdentity
from sentientos.local_model_production_serving import ProductionServingController, ProductionServingError
from sentientos.local_runtime_provisioning import semantic_digest

pytestmark = pytest.mark.no_legacy_skip


class Kernel:
    def __init__(self, outcome=AdmissionOutcome.ALLOW): self.outcome, self.requests = outcome, []
    def admit(self, request):
        self.requests.append(request)
        return SimpleNamespace(outcome=self.outcome, authority_class=request.authority_class, actor=request.actor,
            action_kind=request.action_kind, target_subsystem=request.target_subsystem,
            correlation_id=request.metadata["correlation_id"], admission_decision_ref="kernel_decision:" + request.metadata["correlation_id"])


class Model:
    def __init__(self, identity): self.active_identity, self.closed = identity, False
    def close(self): self.closed = True


def evidence(generation=1):
    proof = {"proof_semantic_digest": "proof-digest", "deployment_receipt_id": "deployment-1"}
    state = {"installation_identity": "install-1", "generation": generation, "model_id": "model-1",
        "artifact_id": "artifact-1", "artifact_path": "/models/exact.gguf", "artifact_sha256": "a" * 64,
        "artifact_size_bytes": 42, "route_id": "route-1", "runtime_id": "runtime-1",
        "interpreter_path": "/runtime/python", "load_configuration": {"n_ctx": 1024, "n_gpu_layers": 0},
        "authority_map_digest": "authority-1", "commissioning_receipt_id": "commissioning-receipt-1",
        "commissioning_receipt_semantic_digest": "commissioning-digest"}
    state["state_semantic_digest"] = semantic_digest(state)
    activation = {"receipt_id": "activation-receipt-1", "receipt_semantic_digest": "activation-digest",
                  "resulting_state_digest": state["state_semantic_digest"]}
    return {"active_state": state, "activation_receipt": activation, "catalog_proof": proof}


@pytest.fixture
def handle(tmp_path):
    registry = InstallationStateRegistry(tmp_path / "custody", _test_only=True)
    return registry.open(InstallationIdentity.parse("install-1"), create=True)


def identity(**changes):
    values = dict(engine="llama_cpp", resolved_artifact_path="/models/exact.gguf",
        semantic_artifact_identity="sha256:" + "a" * 64, model_content_sha256="a" * 64,
        artifact_size_bytes=42, sidecar_metadata_digest=None, configuration_digest="config-1",
        candidate_index=0, posture="production", fallback=False)
    values.update(changes)
    return ActiveModelIdentity(**values)


def controller(monkeypatch, handle, sequence, kernel=None, factory=None):
    values = iter(sequence)
    monkeypatch.setattr("sentientos.local_model_production_serving.verify_current_activation", lambda *a, **k: next(values))
    result = ProductionServingController(handle, kernel or Kernel(), model_factory=factory or (lambda c, l: Model(identity())))
    monkeypatch.setattr(result, "_commissioning_identity", lambda s: identity().to_dict())
    return result


def test_success_loads_once_binds_receipt_and_performs_zero_inference(monkeypatch, handle):
    current = evidence(); made = []
    ctl = controller(monkeypatch, handle, [current, current, current], factory=lambda c, l: made.append(Model(identity())) or made[-1])
    session = ctl.establish()
    assert len(made) == 1 and ctl.current_session() == session
    assert not hasattr(session, "generate") and not hasattr(session, "model")
    receipts = handle.list_regular_names(handle.fixed_object("local-model/serving/receipts"))
    receipt = __import__("json").loads(handle.read_regular(handle.fixed_object("local-model/serving/receipts/" + receipts[0])))
    assert receipt["model_loaded"] is True and receipt["serving_session_bound"] is True
    assert receipt["inference_performed"] is False and receipt["local_model_inference_authority_granted"] is False
    assert handle.list_regular_names(handle.fixed_object("logs/privileges"))


@pytest.mark.parametrize("outcome", [AdmissionOutcome.DENY, AdmissionOutcome.DEFER, AdmissionOutcome.QUARANTINE])
def test_model_serving_admission_precedes_and_blocks_load(monkeypatch, handle, outcome):
    called = [] ; kernel = Kernel(outcome)
    ctl = controller(monkeypatch, handle, [evidence()], kernel=kernel, factory=lambda c, l: called.append(1))
    with pytest.raises(ProductionServingError, match="control_plane_not_allowed"): ctl.establish()
    assert called == [] and ctl.current_session() is None
    assert kernel.requests[0].authority_class is AuthorityClass.MODEL_SERVING


def test_observed_identity_mismatch_closes_without_bind(monkeypatch, handle):
    model = Model(identity(engine="substituted")); ctl = controller(monkeypatch, handle, [evidence()], factory=lambda c, l: model)
    with pytest.raises(ProductionServingError, match="observed_identity_mismatch"): ctl.establish()
    assert model.closed and ctl.current_session() is None


def test_activation_change_during_load_closes_before_bind(monkeypatch, handle):
    model = Model(identity()); ctl = controller(monkeypatch, handle, [evidence(1), evidence(2)], factory=lambda c, l: model)
    with pytest.raises(ProductionServingError, match="activation_changed_during_load"): ctl.establish()
    assert model.closed and ctl.current_session() is None


def test_activation_change_after_bind_invalidates_and_unloads(monkeypatch, handle):
    model = Model(identity()); one, two = evidence(1), evidence(2)
    ctl = controller(monkeypatch, handle, [one, one, two], factory=lambda c, l: model)
    ctl.establish()
    assert ctl.current_session() is None and model.closed
    assert handle.list_regular_names(handle.fixed_object("local-model/serving/invalidations"))


def test_dead_worker_is_not_current(monkeypatch, handle):
    model = Model(identity()); model._process = SimpleNamespace(poll=lambda: 7)
    current = evidence(); ctl = controller(monkeypatch, handle, [current, current, current], factory=lambda c, l: model)
    ctl.establish()
    assert ctl.current_session() is None and model.closed


def test_constructor_has_no_path_runtime_or_preloaded_model_parameters():
    import inspect
    parameters = inspect.signature(ProductionServingController).parameters
    assert not {"model_path", "activation_path", "runtime", "preloaded_model", "autoload"} & set(parameters)
