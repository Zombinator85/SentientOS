"""Explicit one-shot composition of a production model-replacement campaign trial."""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .commissioned_model_evidence import verify_commissioned_model
from .control_plane_kernel import ControlPlaneKernel
from .developmental_model_replacement_campaign import DevelopmentalModelReplacementCampaign
from .developmental_model_replacement_experiment import (
    CognitiveModelIdentity, DevelopmentalModelReplacementError,
    DevelopmentalModelReplacementExperiment, FrozenCausalContext,
    ModelDevelopmentProvenance, ModelReplacementArtifactStore,
)
from .developmental_model_replacement_experimental_serving import (
    ExperimentalModelServingController, ExperimentalCognitiveEndpoint,
    verify_runtime_approval,
)
from .installation_state import InstallationStateHandle
from .local_model_authority import atomic_write_json
from .local_model_runtime_worker import ExactRuntimeLocalModel
from .local_runtime_provisioning import semantic_digest

RECEIPT_SCHEMA = "sentientos.developmental_model_replacement_production_trial_receipt:v1"
POSTURES = {"production_experimental_trial", "synthetic_test_trial"}
_ALIASES = {"", "current", "latest", "default", "any", "*"}


class ProductionTrialError(RuntimeError):
    def __init__(self, code: str): self.code = code; super().__init__(code)


class _IdentityEndpoint:
    def __init__(self, identity: CognitiveModelIdentity) -> None: self.identity = identity
    def current_identity(self) -> CognitiveModelIdentity: return self.identity
    def infer(self, **_: Any) -> Mapping[str, Any]: raise ProductionTrialError("preflight_endpoint_cannot_infer")


def _file_snapshot(path: Path) -> Mapping[str, Any]:
    if not path.exists(): return {"state": "absent"}
    if not path.is_file(): raise ProductionTrialError("canonical_state_not_regular_file")
    data = path.read_bytes()
    return {"state": "present", "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _exact(value: str, label: str) -> str:
    if not value or value.casefold() in _ALIASES or "*" in value or "/" in value or "\\" in value:
        raise ProductionTrialError(label + "_not_exact")
    return value


class DevelopmentalModelReplacementProductionTrialRunner:
    """Compose exactly one next trial; this object owns no cadence or authority."""

    def __init__(self, installation_handle: InstallationStateHandle, control_plane_kernel: ControlPlaneKernel,
                 *, campaign_artifact_root: Path, experiment_artifact_root: Path,
                 model_factory: Callable[[Mapping[str, Any], Mapping[str, Any]], Any] = ExactRuntimeLocalModel,
                 allow_synthetic_evidence_for_tests: bool = False) -> None:
        if not isinstance(installation_handle, InstallationStateHandle):
            raise ProductionTrialError("authenticated_installation_handle_required")
        self._handle, self._kernel = installation_handle, control_plane_kernel
        self._campaign_root, self._experiment_root = Path(campaign_artifact_root), Path(experiment_artifact_root)
        self._factory, self._synthetic = model_factory, allow_synthetic_evidence_for_tests
        self._controller = ExperimentalModelServingController(installation_handle, control_plane_kernel,
            artifact_root=self._experiment_root, model_factory=model_factory,
            allow_synthetic_evidence_for_tests=allow_synthetic_evidence_for_tests)
        installation_handle.ensure_directory(installation_handle.fixed_object(
            "local-model/developmental-model-replacement/production-trials"))

    def _preflight_campaign(self, campaign_id: str, campaign_digest: str, base_protocol_id: str,
                            base_protocol_digest: str, context: FrozenCausalContext,
                            provenance_a: ModelDevelopmentProvenance,
                            provenance_b: ModelDevelopmentProvenance) -> tuple[DevelopmentalModelReplacementCampaign, str | None]:
        protocol = ModelReplacementArtifactStore(self._experiment_root).load_verified_protocol(base_protocol_id, base_protocol_digest)
        context.verify(); provenance_a.verify(protocol.model_a_identity); provenance_b.verify(protocol.model_b_identity)
        preflight = DevelopmentalModelReplacementExperiment(context=context,
            model_a=_IdentityEndpoint(protocol.model_a_identity), model_b=_IdentityEndpoint(protocol.model_b_identity),
            artifact_root=self._experiment_root, model_a_provenance=provenance_a, model_b_provenance=provenance_b)
        if preflight.protocol != protocol: raise ProductionTrialError("base_protocol_inputs_changed")
        campaign = DevelopmentalModelReplacementCampaign.reconstruct(experiment=preflight,
            artifact_root=self._campaign_root, campaign_id=campaign_id)
        if campaign.protocol.campaign_digest != campaign_digest: raise ProductionTrialError("campaign_digest_mismatch")
        state = campaign.store.load_state(campaign.protocol)
        if state["validity"] == "valid_complete" and state["next_trial_id"] is None: return campaign, None
        if state["validity"] != "valid_incomplete" or state["in_progress_trial_id"]:
            raise ProductionTrialError("campaign_not_runnable")
        return campaign, str(state["next_trial_id"])

    def run_one(self, *, campaign_id: str, campaign_digest: str, base_protocol_id: str,
                base_protocol_digest: str, commissioning_receipt_a: str, commissioning_receipt_b: str,
                serving_correlation_a: str, serving_correlation_b: str,
                serving_approval_a: Mapping[str, Any], serving_approval_b: Mapping[str, Any],
                invocation_correlation: str, observation_time: datetime, context: FrozenCausalContext,
                provenance_a: ModelDevelopmentProvenance, provenance_b: ModelDevelopmentProvenance,
                evidence_posture: str) -> Mapping[str, Any]:
        for value, label in ((campaign_id, "campaign_id"), (campaign_digest, "campaign_digest"),
            (base_protocol_id, "base_protocol_id"), (base_protocol_digest, "base_protocol_digest"),
            (commissioning_receipt_a, "commissioning_receipt_a"), (commissioning_receipt_b, "commissioning_receipt_b"),
            (serving_correlation_a, "serving_correlation_a"), (serving_correlation_b, "serving_correlation_b"),
            (invocation_correlation, "invocation_correlation")): _exact(value, label)
        if evidence_posture not in POSTURES: raise ProductionTrialError("evidence_posture_invalid")
        if serving_correlation_a == serving_correlation_b: raise ProductionTrialError("serving_correlations_not_distinct")
        campaign, trial_id = self._preflight_campaign(campaign_id, campaign_digest, base_protocol_id,
            base_protocol_digest, context, provenance_a, provenance_b)
        if trial_id is None:
            return MappingProxyType({"status": "campaign_already_complete", "campaign_id": campaign_id,
                                     "campaign_digest": campaign_digest, "effect_performed": False})

        evidence_a = verify_commissioned_model(self._handle, commissioning_receipt_a,
            allow_synthetic_for_tests=self._synthetic)
        evidence_b = verify_commissioned_model(self._handle, commissioning_receipt_b,
            allow_synthetic_for_tests=self._synthetic)
        protocol = ModelReplacementArtifactStore(self._experiment_root).load_verified_protocol(base_protocol_id, base_protocol_digest)
        if evidence_a.cognitive_identity != protocol.model_a_identity: raise ProductionTrialError("model_a_identity_mismatch")
        if evidence_b.cognitive_identity != protocol.model_b_identity: raise ProductionTrialError("model_b_identity_mismatch")
        if evidence_a.cognitive_identity.semantic_key() == evidence_b.cognitive_identity.semantic_key():
            raise ProductionTrialError("experimental_models_not_distinct")
        intent_a = self._controller.prepare_intent(protocol_id=base_protocol_id, protocol_digest=base_protocol_digest,
            model_role="model_a", commissioning_receipt_id=commissioning_receipt_a, correlation_id=serving_correlation_a)
        intent_b = self._controller.prepare_intent(protocol_id=base_protocol_id, protocol_digest=base_protocol_digest,
            model_role="model_b", commissioning_receipt_id=commissioning_receipt_b, correlation_id=serving_correlation_b)
        approval_a = verify_runtime_approval(serving_approval_a, intent_a, observation_time=observation_time,
            allow_synthetic_for_tests=self._synthetic)
        approval_b = verify_runtime_approval(serving_approval_b, intent_b, observation_time=observation_time,
            allow_synthetic_for_tests=self._synthetic)
        synthetic = (self._synthetic or self._factory is not ExactRuntimeLocalModel
                     or bool(evidence_a.receipt.get("synthetic_test_evidence"))
                     or bool(evidence_b.receipt.get("synthetic_test_evidence"))
                     or bool(approval_a.get("synthetic_test_evidence")) or bool(approval_b.get("synthetic_test_evidence")))
        actual_posture = "synthetic_test_trial" if synthetic else "production_experimental_trial"
        if evidence_posture != actual_posture: raise ProductionTrialError("evidence_posture_mismatch")

        activation_path = self._handle.root / "local-model" / "activation" / "active.json"
        serving_path = self._handle.root / "local-model" / "serving" / "active.json"
        before_activation, before_serving = _file_snapshot(activation_path), _file_snapshot(serving_path)
        before_history = context.history_record_set_digest
        endpoint_a: ExperimentalCognitiveEndpoint | None = None
        endpoint_b: ExperimentalCognitiveEndpoint | None = None
        run: Mapping[str, Any]
        try:
            endpoint_a = self._controller.establish(intent=intent_a, approval=approval_a, observation_time=observation_time)
            endpoint_b = self._controller.establish(intent=intent_b, approval=approval_b, observation_time=observation_time)
            experiment = DevelopmentalModelReplacementExperiment(context=context, model_a=endpoint_a, model_b=endpoint_b,
                artifact_root=self._experiment_root, model_a_provenance=provenance_a, model_b_provenance=provenance_b)
            campaign = DevelopmentalModelReplacementCampaign.reconstruct(experiment=experiment,
                artifact_root=self._campaign_root, campaign_id=campaign_id)
            if campaign.state["next_trial_id"] != trial_id: raise ProductionTrialError("next_trial_changed_before_execution")
            run = campaign.run_next_trial()
        finally:
            if endpoint_b is not None: endpoint_b.close(reason="production_trial_complete")
            if endpoint_a is not None: endpoint_a.close(reason="production_trial_complete")
        if endpoint_a is None or endpoint_b is None or endpoint_a.closure_receipt is None or endpoint_b.closure_receipt is None:
            raise ProductionTrialError("bounded_closure_evidence_missing")
        after_activation, after_serving = _file_snapshot(activation_path), _file_snapshot(serving_path)
        context.verify()
        if before_activation != after_activation: raise ProductionTrialError("canonical_activation_changed")
        if before_serving != after_serving: raise ProductionTrialError("canonical_production_serving_changed")
        if before_history != context.history_record_set_digest: raise ProductionTrialError("developmental_history_changed")
        state = campaign.store.load_state(campaign.protocol)
        observations = list(run["observations"])
        body: dict[str, Any] = {"schema_version": RECEIPT_SCHEMA, "status": "completed_one_trial",
            "campaign_id": campaign_id, "campaign_digest": campaign_digest, "campaign_protocol_digest": campaign.protocol.campaign_digest,
            "trial_id": trial_id, "base_protocol_id": base_protocol_id, "base_protocol_digest": base_protocol_digest,
            "causal_context_id": context.context_id, "causal_context_digest": context.context_digest,
            "model_a_commissioning_receipt_id": commissioning_receipt_a, "model_a_commissioning_receipt_digest": evidence_a.receipt["receipt_semantic_digest"],
            "model_b_commissioning_receipt_id": commissioning_receipt_b, "model_b_commissioning_receipt_digest": evidence_b.receipt["receipt_semantic_digest"],
            "model_a_identity_digest": evidence_a.cognitive_identity.identity_digest, "model_b_identity_digest": evidence_b.cognitive_identity.identity_digest,
            "model_a_serving": {k: endpoint_a.serving_receipt[k] for k in ("receipt_id", "receipt_digest", "serving_lifetime_id", "model_serving_admission_ref")},
            "model_b_serving": {k: endpoint_b.serving_receipt[k] for k in ("receipt_id", "receipt_digest", "serving_lifetime_id", "model_serving_admission_ref")},
            "inference_receipts": [{k: item[k] for k in ("condition_id", "inference_receipt_id", "inference_receipt_digest")} for item in observations],
            "run_id": run["run_id"], "run_digest": run["run_digest"], "updated_campaign_state_digest": state["state_digest"],
            "evidence_posture": actual_posture, "canonical_activation_snapshot": before_activation,
            "canonical_production_serving_snapshot": before_serving, "developmental_history_record_set_digest": before_history,
            "activation_preserved": True, "production_serving_preserved": True, "developmental_history_preserved": True,
            "resident_default_model_preserved": True, "autonomous_repetition_performed": False,
            "invocation_correlation": invocation_correlation,
            "model_a_closure": {k: endpoint_a.closure_receipt[k] for k in ("closure_id", "closure_digest")},
            "model_b_closure": {k: endpoint_b.closure_receipt[k] for k in ("closure_id", "closure_digest")}}
        body["receipt_id"] = "production-model-replacement-trial-" + semantic_digest(body)[:24]
        body["receipt_digest"] = semantic_digest(body)
        path = self._handle.root / "local-model" / "developmental-model-replacement" / "production-trials" / f"{body['receipt_id']}.json"
        if path.exists(): raise ProductionTrialError("production_trial_receipt_already_exists")
        atomic_write_json(path, body)
        return MappingProxyType({"status": "completed_one_trial", "result": dict(run), "receipt": body})


def verify_production_trial_receipt(value: Mapping[str, Any]) -> None:
    body = dict(value); claimed = body.pop("receipt_digest", None)
    if body.get("schema_version") != RECEIPT_SCHEMA or claimed != semantic_digest(body):
        raise ProductionTrialError("production_trial_receipt_tampered")
    if body.get("evidence_posture") not in POSTURES or body.get("autonomous_repetition_performed") is not False:
        raise ProductionTrialError("production_trial_receipt_invalid")
