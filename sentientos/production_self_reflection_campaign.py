"""Fail-closed custody for the production self-reflection A -> B -> A experiment.

This module is deliberately a composer.  Commissioning, serving, activation,
transition, World-State, reconciliation, inference and scoring remain owned by
their existing implementations.  The composer binds their receipts and calls a
supplied live executor; it neither creates approvals nor provides a synthetic
fallback.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from .local_model_authority import atomic_write_json, digest_payload
from .resident_cognitive_model_transition_experiment import PHASES
from .self_model_intervention_experiment import CONDITION_ORDER, score_assessment

PROTOCOL_SCHEMA = "sentientos.production_self_reflection_protocol:v1"
READINESS_SCHEMA = "sentientos.production_self_reflection_readiness:v1"
CAMPAIGN_SCHEMA = "sentientos.production_self_reflection_campaign_state:v1"
RECEIPT_SCHEMA = "sentientos.production_self_reflection_trial_receipt:v1"
REPORT_SCHEMA = "sentientos.production_self_reflection_campaign_report:v1"
SCORER = "deterministic_exact_evidence_key:v1"
MIN_TRIALS, MAX_TRIALS = 2, 32
ALIASES = {"", "latest", "current", "default", "any", "*"}
COMPONENTS = ("commissioning", "artifact_custody", "runtime_workers", "approvals",
              "resident_serving", "activation", "inference", "world_state_inputs",
              "self_model_custody", "scorer", "live_transition_execution")


class ProductionSelfReflectionError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _digest(value: Any) -> str:
    result: str = digest_payload(value)
    return "sha256:" + result


def _exact(value: object, label: str) -> str:
    text = str(value)
    if text.casefold() in ALIASES or "*" in text or "/" in text or "\\" in text:
        raise ProductionSelfReflectionError(label + "_not_exact")
    return text


def _immutable(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProductionSelfReflectionError("immutable_artifact_tampered") from exc
        if prior != dict(value):
            raise ProductionSelfReflectionError("immutable_artifact_collision")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, value)


@dataclass(frozen=True)
class ProductionSelfReflectionProtocol:
    protocol_id: str
    protocol_digest: str
    installation_identity: str
    software_generation: str
    runtime_configuration: Mapping[str, Any]
    requested_evidence_posture: str
    model_a: Mapping[str, Any]
    model_b: Mapping[str, Any]
    persistent_state: Mapping[str, Any]
    assessment: Mapping[str, Any]
    transition: Mapping[str, Any]
    campaign_policy: Mapping[str, Any]
    schema_version: str = PROTOCOL_SCHEMA
    grants_authority: bool = False

    @classmethod
    def create(cls, *, installation_identity: str, software_generation: str,
               runtime_configuration: Mapping[str, Any], model_a: Mapping[str, Any],
               model_b: Mapping[str, Any], persistent_state: Mapping[str, Any],
               assessment: Mapping[str, Any], transition: Mapping[str, Any],
               trial_ids: Sequence[str], requested_evidence_posture: str = "production") -> "ProductionSelfReflectionProtocol":
        ids = tuple(_exact(x, "trial_id") for x in trial_ids)
        if not MIN_TRIALS <= len(ids) <= MAX_TRIALS or len(set(ids)) != len(ids):
            raise ProductionSelfReflectionError("trial_inventory_invalid")
        policy = {"planned_trial_count": len(ids), "trial_ids": ids, "silent_retries": False,
                  "trial_replacement": False, "cherry_picking": False,
                  "retain_negative_null_unstable_interrupted": True, "autonomous_repetition": False}
        raw = cls("", "", _exact(installation_identity, "installation_identity"),
                  _exact(software_generation, "software_generation"), dict(runtime_configuration),
                  requested_evidence_posture, dict(model_a), dict(model_b), dict(persistent_state),
                  dict(assessment), dict(transition), policy)
        raw._validate_bindings()
        semantic = asdict(raw); semantic.pop("protocol_id"); semantic.pop("protocol_digest")
        digest = _digest(semantic)
        return replace(raw, protocol_id="production-self-reflection-" + digest[7:31], protocol_digest=digest)

    def _validate_bindings(self) -> None:
        required_model = {"commissioning_receipt_id", "commissioning_receipt_digest", "cognitive_identity",
            "artifact_digest", "artifact_size", "development_provenance_digest", "serving_configuration_digest",
            "activation_approval_id", "serving_approval_id", "inference_authority_map_id"}
        for role, model in (("model_a", self.model_a), ("model_b", self.model_b)):
            if not required_model <= set(model): raise ProductionSelfReflectionError(role + "_binding_incomplete")
            for key in required_model - {"artifact_size"}: _exact(model[key], role + "_" + key)
            if not isinstance(model["artifact_size"], int) or model["artifact_size"] < 1:
                raise ProductionSelfReflectionError(role + "_artifact_size_invalid")
        if self.model_a["cognitive_identity"] == self.model_b["cognitive_identity"]:
            raise ProductionSelfReflectionError("cognitive_identities_not_distinct")
        required_state = {"developmental_history_boundary_digest", "composition_state_digest",
            "initial_reconciliation_id", "initial_reconciliation_digest", "projection_policy",
            "assessment_claim_inventory_digest", "world_state_id", "world_state_digest"}
        if not required_state <= set(self.persistent_state): raise ProductionSelfReflectionError("persistent_state_binding_incomplete")
        required_assessment = {"question_set_digest", "answer_key_digest", "scorer_version", "scorer_digest",
            "projection_id", "projection_digest", "prompt_construction_digest", "inference_budget",
            "generation_parameters", "abstention_format", "citation_format", "condition_order"}
        if not required_assessment <= set(self.assessment): raise ProductionSelfReflectionError("assessment_binding_incomplete")
        if tuple(self.assessment["condition_order"]) != CONDITION_ORDER or self.assessment["scorer_version"] != SCORER:
            raise ProductionSelfReflectionError("assessment_contract_mismatch")
        if tuple(self.transition.get("phase_order", ())) != PHASES:
            raise ProductionSelfReflectionError("transition_protocol_mismatch")
        for key in ("protocol_id", "protocol_digest", "journal_custody", "journal_identity",
                    "installation_relative_custody", "quiescence_semantics", "failure_posture"):
            if key not in self.transition: raise ProductionSelfReflectionError("transition_binding_incomplete")
        if self.requested_evidence_posture != "production":
            raise ProductionSelfReflectionError("production_posture_required")

    def verify(self) -> None:
        self._validate_bindings()
        semantic = asdict(self); semantic.pop("protocol_id"); semantic.pop("protocol_digest")
        digest = _digest(semantic)
        if self.schema_version != PROTOCOL_SCHEMA or self.grants_authority or self.protocol_digest != digest \
                or self.protocol_id != "production-self-reflection-" + digest[7:31]:
            raise ProductionSelfReflectionError("protocol_tampered")


def reconstruct_protocol(value: Mapping[str, Any]) -> ProductionSelfReflectionProtocol:
    try:
        protocol = ProductionSelfReflectionProtocol(**dict(value)); protocol.verify(); return protocol
    except (KeyError, TypeError, ProductionSelfReflectionError) as exc:
        raise ProductionSelfReflectionError("protocol_tampered") from exc


def derive_evidence_posture(components: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    synthetic = tuple(name for name in COMPONENTS if components.get(name) != "nonsynthetic")
    return ("production_experimental_evidence", ()) if not synthetic else ("synthetic_or_rehearsal", synthetic)


def verify_production_readiness(protocol: ProductionSelfReflectionProtocol, observed: Mapping[str, Any],
                                *, artifact_path: Path | None = None) -> Mapping[str, Any]:
    """Mechanically classify supplied observations; the artifact grants no authority."""
    protocol.verify()
    checks = {
        "authenticated_installation_custody": observed.get("installation_identity") == protocol.installation_identity,
        "longitudinal_self_model_custody": observed.get("reconciliation_digest") == protocol.persistent_state["initial_reconciliation_digest"],
        "developmental_history_custody": observed.get("developmental_history_boundary_digest") == protocol.persistent_state["developmental_history_boundary_digest"],
        "active_resident_model": observed.get("resident_cognitive_identity") == protocol.model_a["cognitive_identity"],
        "model_a": observed.get("model_a_available") is True,
        "model_b": observed.get("model_b_available") is True,
        "commissioning": observed.get("commissioning_valid") is True,
        "model_artifacts": observed.get("model_artifacts_valid") is True,
        "runtime_backend": observed.get("runtime_backend_available") is True,
        "activation_approvals": observed.get("activation_approvals_valid") is True,
        "serving_approvals": observed.get("serving_approvals_valid") is True,
        "inference_admission": observed.get("inference_admission_valid") is True,
        "transition_protocol": observed.get("transition_protocol_digest") == protocol.transition["protocol_digest"],
        "stable_serving_slot": observed.get("stable_serving_slot_valid") is True,
        "quiescence_gate": observed.get("live_quiescence_gate") is True,
        "required_roots": observed.get("required_roots_available") is True,
        "assessment_protocol": observed.get("assessment_protocol_valid") is True,
        "external_scorer": observed.get("scorer_digest") == protocol.assessment["scorer_digest"],
        "campaign_state": observed.get("campaign_state_valid") is True,
        "prior_trial_resolved": observed.get("prior_trial_interrupted") is False,
        "transition_journal": observed.get("transition_journal_interrupted") is False,
        "canonical_state": observed.get("canonical_state_conflict") is False,
    }
    raw_components = observed.get("evidence_components", {})
    components = raw_components if isinstance(raw_components, Mapping) else {}
    posture, seams = derive_evidence_posture(components)
    classes: list[str] = []
    ordered = (("model_a", "missing_model_a"), ("model_b", "missing_model_b"),
        ("commissioning", "commissioning_invalid"), ("activation_approvals", "approval_missing"),
        ("serving_approvals", "approval_missing"), ("transition_protocol", "transition_protocol_mismatch"),
        ("longitudinal_self_model_custody", "self_model_custody_invalid"),
        ("developmental_history_custody", "developmental_history_boundary_changed"),
        ("runtime_backend", "runtime_backend_unavailable"), ("prior_trial_resolved", "prior_trial_interrupted"),
        ("transition_journal", "transition_journal_interrupted"), ("canonical_state", "canonical_state_conflict"))
    for check, classification in ordered:
        if not checks[check] and classification not in classes: classes.append(classification)
    if seams: classes.append("synthetic_component_detected")
    for key, passed in checks.items():
        if (not passed and not any(key == pair[0] for pair in ordered)
                and "insufficient_execution_environment" not in classes):
            classes.append("insufficient_execution_environment")
    ready = all(checks.values()) and not seams
    body: dict[str, Any] = {"schema_version": READINESS_SCHEMA, "protocol_id": protocol.protocol_id,
        "protocol_digest": protocol.protocol_digest, "status": "production_trial_ready" if ready else "production_trial_not_ready",
        "classifications": ["production_trial_ready"] if ready else classes, "checks": checks,
        "derived_evidence_posture": posture, "synthetic_components": seams,
        "grants_authority": False, "effect_performed": False}
    body["readiness_id"] = "production-readiness-" + _digest(body)[7:31]
    body["readiness_digest"] = _digest(body)
    if artifact_path is not None: _immutable(artifact_path, body)
    return MappingProxyType(body)


class ProductionSelfReflectionCampaign:
    """Immutable protocol plus mutable digest-bound progress; interruption is terminal."""
    def __init__(self, root: Path, protocol: ProductionSelfReflectionProtocol):
        self.root, self.protocol = Path(root), protocol
        self.protocol_path = self.root / "protocol.json"; self.state_path = self.root / "state.json"

    @classmethod
    def create(cls, root: Path, protocol: ProductionSelfReflectionProtocol) -> "ProductionSelfReflectionCampaign":
        protocol.verify(); campaign = cls(root, protocol); _immutable(campaign.protocol_path, asdict(protocol))
        campaign._write({"completed_trials": [], "next_trial_id": protocol.campaign_policy["trial_ids"][0],
                         "in_progress_trial_id": None, "validity": "valid_incomplete", "failure_reason": None})
        return campaign

    @classmethod
    def reconstruct(cls, root: Path) -> "ProductionSelfReflectionCampaign":
        try: protocol = reconstruct_protocol(json.loads((Path(root) / "protocol.json").read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc: raise ProductionSelfReflectionError("campaign_protocol_unavailable") from exc
        campaign = cls(root, protocol); state = campaign.state()
        if state["in_progress_trial_id"]:
            campaign._write({**state, "validity": "invalid_interrupted", "failure_reason": "prior_trial_interrupted"})
            _immutable(campaign.root / "failures" / f"{state['in_progress_trial_id']}.json",
                       {"trial_id": state["in_progress_trial_id"], "classification": "prior_trial_interrupted", "retry_permitted": False})
            raise ProductionSelfReflectionError("prior_trial_interrupted")
        return campaign

    def _write(self, value: Mapping[str, Any]) -> Mapping[str, Any]:
        body = {"schema_version": CAMPAIGN_SCHEMA, "protocol_id": self.protocol.protocol_id,
                "protocol_digest": self.protocol.protocol_digest, **dict(value)}
        body.pop("state_digest", None); body["state_digest"] = _digest(body)
        self.state_path.parent.mkdir(parents=True, exist_ok=True); atomic_write_json(self.state_path, body); return body

    def state(self) -> Mapping[str, Any]:
        try: value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise ProductionSelfReflectionError("campaign_state_unavailable") from exc
        claimed = value.pop("state_digest", None)
        if claimed != _digest(value) or value.get("protocol_digest") != self.protocol.protocol_digest:
            raise ProductionSelfReflectionError("campaign_state_tampered")
        return MappingProxyType({**value, "state_digest": claimed})

    def run_one(self, readiness: Mapping[str, Any], executor: Callable[[str, ProductionSelfReflectionProtocol], Mapping[str, Any]]) -> Mapping[str, Any]:
        state = self.state()
        if readiness.get("status") != "production_trial_ready": raise ProductionSelfReflectionError("production_trial_not_ready")
        if state["validity"] != "valid_incomplete" or state["in_progress_trial_id"] or not state["next_trial_id"]:
            raise ProductionSelfReflectionError("campaign_not_runnable")
        trial_id = str(state["next_trial_id"]); self._write({**state, "in_progress_trial_id": trial_id})
        try: evidence = dict(executor(trial_id, self.protocol)); receipt = make_trial_receipt(self.protocol, trial_id, evidence)
        except Exception:
            self._write({**self.state(), "validity": "invalid_interrupted", "failure_reason": "trial_interrupted_no_retry"})
            raise
        _immutable(self.root / "receipts" / f"{trial_id}.json", receipt)
        completed = list(state["completed_trials"]) + [{"trial_id": trial_id, "receipt_id": receipt["receipt_id"], "receipt_digest": receipt["receipt_digest"]}]
        ids = list(self.protocol.campaign_policy["trial_ids"]); index = len(completed)
        self._write({"completed_trials": completed, "next_trial_id": ids[index] if index < len(ids) else None,
                     "in_progress_trial_id": None, "validity": "valid_complete" if index == len(ids) else "valid_incomplete",
                     "failure_reason": None})
        return MappingProxyType(receipt)

    def report(self) -> Mapping[str, Any]:
        state = self.state()
        if state["validity"] != "valid_complete": raise ProductionSelfReflectionError("campaign_incomplete")
        receipts = [verify_trial_receipt(json.loads((self.root / "receipts" / f"{x['trial_id']}.json").read_text())) for x in state["completed_trials"]]
        scores = {condition: [r["condition_scores"][condition]["counts"] for r in receipts] for condition in CONDITION_ORDER}
        body: dict[str, Any] = {"schema_version": REPORT_SCHEMA, "protocol_id": self.protocol.protocol_id,
            "planned_trial_count": len(receipts), "valid_completed_trials": len(receipts), "interrupted_trials": 0,
            "condition_scores": scores, "restoration_results": [r["restoration_result"] for r in receipts],
            "descriptive_only": True, "negative_null_unstable_retained": True,
            "unsupported_inferences": ["consciousness", "identity", "learning", "sentience", "guaranteed_improvement"]}
        body["report_digest"] = _digest(body); _immutable(self.root / "report.json", body); return MappingProxyType(body)


def make_trial_receipt(protocol: ProductionSelfReflectionProtocol, trial_id: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    required = {"installation_identity", "software_generation_before", "software_generation_after", "transition_stage_receipts",
        "transition_journal_identity", "world_state_identities", "self_model_reconciliations", "self_model_projections",
        "developmental_history_boundary_digest", "condition_inference_receipts", "condition_answers", "pre_resident_identity",
        "post_resident_identity", "pre_self_model_generation", "post_self_model_generation", "restoration_result", "evidence_components"}
    if not required <= set(evidence): raise ProductionSelfReflectionError("trial_evidence_incomplete")
    posture, seams = derive_evidence_posture(evidence["evidence_components"])
    if posture != "production_experimental_evidence": raise ProductionSelfReflectionError("synthetic_component_detected")
    if evidence["pre_resident_identity"] != protocol.model_a["cognitive_identity"] or evidence["post_resident_identity"] != protocol.model_a["cognitive_identity"]:
        raise ProductionSelfReflectionError("restored_a_identity_mismatch")
    stages = tuple(x["phase"] for x in evidence["transition_stage_receipts"])
    if stages != PHASES[1:]: raise ProductionSelfReflectionError("transition_stage_order_mismatch")
    projections = evidence["self_model_projections"]
    if any(not item.get("prior_tick_proven") for item in projections): raise ProductionSelfReflectionError("prior_tick_firewall_breached")
    answer_key = evidence.get("answer_key")
    if not isinstance(answer_key, Mapping) or _digest(answer_key) != protocol.assessment["answer_key_digest"]:
        raise ProductionSelfReflectionError("external_scorer_custody_mismatch")
    scores = {condition: score_assessment(answer_key=answer_key, answers=evidence["condition_answers"][condition]) for condition in CONDITION_ORDER}
    body: dict[str, Any] = {"schema_version": RECEIPT_SCHEMA, "protocol_id": protocol.protocol_id,
        "protocol_digest": protocol.protocol_digest, "trial_id": trial_id, "installation_identity": evidence["installation_identity"],
        "software_generation_before": evidence["software_generation_before"], "software_generation_after": evidence["software_generation_after"],
        "model_a_commissioning": {k: protocol.model_a[k] for k in ("commissioning_receipt_id", "commissioning_receipt_digest")},
        "model_b_commissioning": {k: protocol.model_b[k] for k in ("commissioning_receipt_id", "commissioning_receipt_digest")},
        "transition_stage_receipts": evidence["transition_stage_receipts"], "transition_journal_identity": evidence["transition_journal_identity"],
        "world_state_identities": evidence["world_state_identities"], "self_model_reconciliations": evidence["self_model_reconciliations"],
        "self_model_projections": projections, "developmental_history_boundary_digest": evidence["developmental_history_boundary_digest"],
        "condition_inference_receipts": evidence["condition_inference_receipts"], "condition_answer_digests": {k: _digest(v) for k, v in evidence["condition_answers"].items()},
        "condition_scores": scores, "pre_resident_identity": evidence["pre_resident_identity"], "post_resident_identity": evidence["post_resident_identity"],
        "pre_self_model_generation": evidence["pre_self_model_generation"], "post_self_model_generation": evidence["post_self_model_generation"],
        "restoration_result": evidence["restoration_result"], "evidence_posture": posture, "synthetic_components": seams,
        "status": "completed", "production_evidence_collected": True, "failure_or_interruption": None,
        "autonomous_repetition_performed": False, "model_output_has_scoring_authority": False}
    body["receipt_id"] = "production-self-reflection-trial-" + _digest(body)[7:31]
    body["receipt_digest"] = _digest(body); return body


def verify_trial_receipt(value: Mapping[str, Any]) -> Mapping[str, Any]:
    body = dict(value); claimed = body.pop("receipt_digest", None)
    if body.get("schema_version") != RECEIPT_SCHEMA or claimed != _digest(body) or body.get("evidence_posture") != "production_experimental_evidence":
        raise ProductionSelfReflectionError("trial_receipt_tampered")
    return MappingProxyType(dict(value))


__all__ = ["COMPONENTS", "ProductionSelfReflectionCampaign", "ProductionSelfReflectionError",
           "ProductionSelfReflectionProtocol", "derive_evidence_posture", "make_trial_receipt",
           "reconstruct_protocol", "verify_production_readiness", "verify_trial_receipt"]
