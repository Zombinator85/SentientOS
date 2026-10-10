"""Deterministic embodied consequence evidence and developmental experiments.

Every record in this module is evidence or a proposal.  Nothing here performs an
embodied action, adopts a body, grants authority, or promotes interpretation to
current truth.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, cast

EXPECTATION_SCHEMA = "sentientos.embodied_action_expectation:v1"
REPORT_SCHEMA = "sentientos.avatar_renderer_report:v1"
OBSERVATION_SCHEMA = "sentientos.avatar_independent_observation:v1"
ATTRIBUTION_SCHEMA = "sentientos.embodied_consequence_attribution:v1"
COMPARISON_SCHEMA = "sentientos.embodied_prediction_comparison:v1"
STRATEGY_SCHEMA = "sentientos.embodied_strategy_proposal:v1"
EXPERIMENT_SCHEMA = "sentientos.embodied_strategy_experiment:v1"
LEGACY_EXPERIMENT_RESULT_SCHEMA = "sentientos.embodied_strategy_experiment_result:v1"
EXPERIMENT_RESULT_SCHEMA = "sentientos.embodied_strategy_experiment_result:v2"
MAX_STRATEGY_CONTEXT_BYTES = 1_048_576
MAX_CONSEQUENCE_ARTIFACT_BYTES = 2_097_152
_CONSEQUENCE_KINDS = {"expectations", "reports", "observations", "attributions", "comparisons", "strategy-experiments"}
_CONSEQUENCE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}:[0-9a-f]{24}\Z")
_ARTIFACT_IDENTITIES = {
    "expectations": ("expectation_id", "expectation_digest", "expectation"),
    "reports": ("report_id", "report_digest", "renderer-report"),
    "observations": ("observation_id", "observation_digest", "independent-observation"),
    "attributions": ("attribution_id", "attribution_digest", "consequence"),
    "comparisons": ("comparison_id", "comparison_digest", "prediction-comparison"),
    "strategy-experiments": ("experiment_result_id", "experiment_result_digest", "strategy-experiment"),
}
FALSE_AUTHORITY = {"effect_authority": False, "adoption_authority": False,
                   "observation_authority": False, "goal_authority": False,
                   "authoring_authority": False, "execution_authority": False}
ATTRIBUTION_RESULTS = frozenset({"expectation_satisfied", "expectation_partially_satisfied",
    "expectation_contradicted", "observation_missing", "renderer_report_only", "indeterminate",
    "execution_failed", "body_generation_mismatch", "correlation_mismatch"})
CAUSAL_POSTURES = frozenset({"self_command_correlated", "renderer_internal_only",
    "independent_environment_observation", "external_interference_possible",
    "causal_attribution_insufficient"})
POSTURES = frozenset({"synthetic_test", "rehearsal", "production"})


class EmbodiedConsequenceError(ValueError):
    """Fail-closed contract or provenance error."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise EmbodiedConsequenceError("timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise EmbodiedConsequenceError("timestamp_timezone_required")
    return parsed


def _identity(prefix: str, payload: Mapping[str, Any]) -> tuple[str, str]:
    dg = digest(payload)
    return f"{prefix}:{dg[7:31]}", dg


def _validate_authority(authority: Mapping[str, bool]) -> None:
    if dict(authority) != FALSE_AUTHORITY:
        raise EmbodiedConsequenceError("authority_must_be_all_false")


@dataclass(frozen=True)
class EmbodiedActionExpectation:
    expectation_id: str
    expectation_digest: str
    installation_body_id: str
    body_id: str
    body_generation: int
    body_manifest_digest: str
    handoff_id: str
    handoff_digest: str
    renderer_interface_id: str
    requested: Mapping[str, Any]
    predicted_observables: Mapping[str, Any]
    observable_fields: tuple[str, ...]
    comparison_policy: Mapping[str, Mapping[str, Any]]
    expected_observation_source_class: str
    correlation_id: str
    causal_principal_binding_digest: str | None
    created_at: str
    expires_at: str
    authority: Mapping[str, bool]
    schema_version: str = EXPECTATION_SCHEMA

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("expectation_id"); value.pop("expectation_digest"); return value


def make_expectation(**kwargs: Any) -> EmbodiedActionExpectation:
    raw = EmbodiedActionExpectation("", "", authority=dict(FALSE_AUTHORITY), **kwargs)
    verify_expectation(raw, identity_required=False)
    eid, dg = _identity("expectation", raw.semantic_payload())
    return replace(raw, expectation_id=eid, expectation_digest=dg)


def verify_expectation(value: EmbodiedActionExpectation, *, identity_required: bool = True) -> None:
    if value.schema_version != EXPECTATION_SCHEMA or value.body_generation < 1:
        raise EmbodiedConsequenceError("expectation_shape_invalid")
    _validate_authority(value.authority)
    if (not value.observable_fields or len(value.observable_fields) != len(set(value.observable_fields))
            or set(value.observable_fields) != set(value.predicted_observables)
            or set(value.observable_fields) != set(value.comparison_policy)):
        raise EmbodiedConsequenceError("expectation_observable_contract_invalid")
    if _time(value.expires_at) <= _time(value.created_at):
        raise EmbodiedConsequenceError("expectation_freshness_invalid")
    for field, policy in value.comparison_policy.items():
        if set(policy) - {"kind", "tolerance"} or policy.get("kind") not in {"exact", "numeric_tolerance"}:
            raise EmbodiedConsequenceError("comparison_policy_invalid")
        if policy["kind"] == "numeric_tolerance" and (type(policy.get("tolerance")) not in (int, float) or policy["tolerance"] < 0):
            raise EmbodiedConsequenceError("comparison_tolerance_invalid")
    if identity_required and (value.expectation_id, value.expectation_digest) != _identity("expectation", value.semantic_payload()):
        raise EmbodiedConsequenceError("expectation_digest_mismatch")


@dataclass(frozen=True)
class AvatarRendererReport:
    report_id: str
    report_digest: str
    renderer_id: str
    renderer_implementation: str
    renderer_version: str
    renderer_interface_id: str
    body_generation: int
    artifact_digest: str
    manifest_digest: str
    handoff_id: str
    handoff_digest: str
    correlation_id: str
    requested: Mapping[str, Any]
    applied: Mapping[str, Any]
    started_at: str
    completed_at: str
    renderer_status: str
    source_digest: str
    posture: str
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    authority: Mapping[str, bool]
    schema_version: str = REPORT_SCHEMA

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("report_id"); value.pop("report_digest"); return value


def make_renderer_report(**kwargs: Any) -> AvatarRendererReport:
    raw = AvatarRendererReport("", "", authority=dict(FALSE_AUTHORITY), **kwargs)
    verify_renderer_report(raw, identity_required=False)
    rid, dg = _identity("renderer-report", raw.semantic_payload())
    return replace(raw, report_id=rid, report_digest=dg)


def verify_renderer_report(value: AvatarRendererReport, *, identity_required: bool = True) -> None:
    if value.schema_version != REPORT_SCHEMA or value.posture not in POSTURES or value.body_generation < 1:
        raise EmbodiedConsequenceError("renderer_report_shape_invalid")
    _validate_authority(value.authority)
    if _time(value.completed_at) < _time(value.started_at) or value.renderer_status not in {"applied", "failed", "partial"}:
        raise EmbodiedConsequenceError("renderer_report_status_or_timing_invalid")
    if identity_required and (value.report_id, value.report_digest) != _identity("renderer-report", value.semantic_payload()):
        raise EmbodiedConsequenceError("renderer_report_digest_mismatch")


@dataclass(frozen=True)
class IndependentConsequenceObservation:
    observation_id: str
    observation_digest: str
    observer_id: str
    observation_source_class: str
    body_generation: int
    expectation_id: str
    expectation_digest: str
    handoff_id: str
    handoff_digest: str
    renderer_report_id: str | None
    renderer_report_digest: str | None
    correlation_id: str
    observed: Mapping[str, Any]
    observed_at: str
    confidence: str
    quality: str
    source_digest: str
    posture: str
    authority: Mapping[str, bool]
    schema_version: str = OBSERVATION_SCHEMA

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("observation_id"); value.pop("observation_digest"); return value


def make_independent_observation(**kwargs: Any) -> IndependentConsequenceObservation:
    supplied = dict(kwargs); supplied.setdefault("authority", dict(FALSE_AUTHORITY))
    raw = IndependentConsequenceObservation("", "", **supplied)
    verify_independent_observation(raw, identity_required=False)
    oid, dg = _identity("independent-observation", raw.semantic_payload())
    return replace(raw, observation_id=oid, observation_digest=dg)


def verify_independent_observation(value: IndependentConsequenceObservation, *, identity_required: bool = True) -> None:
    if value.schema_version != OBSERVATION_SCHEMA or value.posture not in POSTURES or value.body_generation < 1:
        raise EmbodiedConsequenceError("independent_observation_shape_invalid")
    if value.observation_source_class in {"renderer", "renderer_report", "renderer_internal"}:
        raise EmbodiedConsequenceError("renderer_cannot_be_independent_observer")
    _validate_authority(value.authority); _time(value.observed_at)
    if (value.renderer_report_id is None) != (value.renderer_report_digest is None):
        raise EmbodiedConsequenceError("observation_renderer_binding_incomplete")
    if identity_required and (value.observation_id, value.observation_digest) != _identity("independent-observation", value.semantic_payload()):
        raise EmbodiedConsequenceError("independent_observation_digest_mismatch")


class RendererTestBackend(Protocol):
    def render_test(self, handoff: Mapping[str, Any]) -> AvatarRendererReport: ...


class IndependentObserver(Protocol):
    def observe(self, *, expectation: EmbodiedActionExpectation, handoff: Mapping[str, Any],
                report: AvatarRendererReport | None) -> IndependentConsequenceObservation: ...


class SyntheticRenderer:
    """CI renderer role; its report is never independent observation."""
    def __init__(self, *, applied: Mapping[str, Any], started_at: str, completed_at: str) -> None:
        self.applied, self.started_at, self.completed_at = dict(applied), started_at, completed_at

    def render_test(self, handoff: Mapping[str, Any]) -> AvatarRendererReport:
        requested = {"pose": handoff["requested_test_pose"], "expression": handoff["requested_test_expression"]}
        return make_renderer_report(renderer_id="synthetic-renderer", renderer_implementation="sentientos.synthetic_renderer",
            renderer_version="1", renderer_interface_id=handoff["renderer_interface_id"], body_generation=handoff["body_generation"],
            artifact_digest=handoff["artifact_sha256"], manifest_digest=handoff["body_manifest_digest"],
            handoff_id=handoff["handoff_id"], handoff_digest=handoff["handoff_digest"], correlation_id=handoff["correlation_id"],
            requested=requested, applied=self.applied, started_at=self.started_at, completed_at=self.completed_at,
            renderer_status="applied", source_digest=digest({"role":"synthetic-renderer","applied":self.applied}),
            posture="synthetic_test", warnings=(), errors=())


class SyntheticIndependentObserver:
    """Separate CI observer role with fixture-selected observations."""
    def __init__(self, *, observer_id: str, observed: Mapping[str, Any], observed_at: str) -> None:
        self.observer_id, self.observed, self.observed_at = observer_id, dict(observed), observed_at

    def observe(self, *, expectation: EmbodiedActionExpectation, handoff: Mapping[str, Any],
                report: AvatarRendererReport | None) -> IndependentConsequenceObservation:
        return make_independent_observation(observer_id=self.observer_id, observation_source_class="synthetic_independent_fixture",
            body_generation=handoff["body_generation"], expectation_id=expectation.expectation_id,
            expectation_digest=expectation.expectation_digest, handoff_id=handoff["handoff_id"], handoff_digest=handoff["handoff_digest"],
            renderer_report_id=report.report_id if report else None, renderer_report_digest=report.report_digest if report else None,
            correlation_id=handoff["correlation_id"], observed=self.observed, observed_at=self.observed_at,
            confidence="fixture_exact", quality="synthetic_fixture", source_digest=digest({"observer":self.observer_id,"observed":self.observed}),
            posture="synthetic_test")


def _compare(expectation: EmbodiedActionExpectation, observation: IndependentConsequenceObservation | None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    counts = {"satisfied": 0, "contradicted": 0, "missing": 0, "indeterminate": 0}
    for field in expectation.observable_fields:
        expected = expectation.predicted_observables[field]; policy = expectation.comparison_policy[field]
        observed = None if observation is None else observation.observed.get(field)
        row: dict[str, Any] = {"field":field, "expected_value":expected, "observed_value":observed,
            "comparison_policy":dict(policy), "expectation_id":expectation.expectation_id,
            "observation_id":observation.observation_id if observation else None,
            "expectation_digest":expectation.expectation_digest,
            "observation_digest":observation.observation_digest if observation else None}
        if observation is None or field not in observation.observed:
            result = "missing"; row["missing_observation"] = True
        elif policy["kind"] == "exact":
            result = "satisfied" if expected == observed else "contradicted"
            row["categorical_mismatch"] = None if result == "satisfied" else {"expected":expected,"observed":observed}
            row["missing_observation"] = False
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool) and isinstance(observed, (int, float)) and not isinstance(observed, bool):
            signed = float(observed) - float(expected); absolute = abs(signed)
            row.update({"signed_delta":signed,"absolute_delta":absolute,"missing_observation":False})
            result = "satisfied" if absolute <= float(cast(float, policy["tolerance"])) else "contradicted"
        else:
            result = "indeterminate"; row["missing_observation"] = False
        row["result"] = result; counts[result] += 1; rows.append(row)
    return rows, counts


def evaluate_consequence(*, expectation: EmbodiedActionExpectation, handoff: Mapping[str, Any],
                         current_body: Mapping[str, Any], renderer_report: AvatarRendererReport | None = None,
                         observation: IndependentConsequenceObservation | None = None,
                         fulfillment_receipt: Mapping[str, Any] | None = None,
                         causal_principal_binding_digest: str | None = None,
                         measured_evidence: Sequence[Mapping[str, Any]] = (), evaluated_at: str) -> tuple[dict[str, Any], dict[str, Any]]:
    verify_expectation(expectation)
    if renderer_report: verify_renderer_report(renderer_report)
    if observation: verify_independent_observation(observation)
    now = _time(evaluated_at)
    mismatch = False
    required = (expectation.handoff_id == handoff.get("handoff_id"), expectation.handoff_digest == handoff.get("handoff_digest"),
        expectation.correlation_id == handoff.get("correlation_id"), expectation.body_manifest_digest == handoff.get("body_manifest_digest"))
    mismatch = not all(required)
    generation_mismatch = expectation.body_generation != handoff.get("body_generation") or expectation.body_generation != current_body.get("body_generation")
    if renderer_report:
        mismatch |= any((renderer_report.handoff_id != expectation.handoff_id, renderer_report.handoff_digest != expectation.handoff_digest,
            renderer_report.correlation_id != expectation.correlation_id, renderer_report.artifact_digest != handoff.get("artifact_sha256"),
            renderer_report.manifest_digest != expectation.body_manifest_digest))
        generation_mismatch |= renderer_report.body_generation != expectation.body_generation
    if observation:
        mismatch |= any((observation.expectation_id != expectation.expectation_id, observation.expectation_digest != expectation.expectation_digest,
            observation.handoff_id != expectation.handoff_id, observation.handoff_digest != expectation.handoff_digest,
            observation.correlation_id != expectation.correlation_id))
        generation_mismatch |= observation.body_generation != expectation.body_generation
        if renderer_report and (observation.renderer_report_id != renderer_report.report_id or observation.renderer_report_digest != renderer_report.report_digest): mismatch = True
        if _time(observation.observed_at) < _time(renderer_report.started_at if renderer_report else expectation.created_at):
            raise EmbodiedConsequenceError("observation_predates_command")
    rows, counts = _compare(expectation, observation)
    stale = now > _time(expectation.expires_at)
    if generation_mismatch: classification = "body_generation_mismatch"
    elif mismatch: classification = "correlation_mismatch"
    elif stale: classification = "indeterminate"
    elif renderer_report and renderer_report.renderer_status == "failed": classification = "execution_failed"
    elif observation is None: classification = "renderer_report_only" if renderer_report else "observation_missing"
    elif counts["contradicted"] and counts["satisfied"]: classification = "expectation_partially_satisfied"
    elif counts["contradicted"]: classification = "expectation_contradicted"
    elif counts["missing"] or counts["indeterminate"]: classification = "indeterminate"
    else: classification = "expectation_satisfied"
    if observation and classification == "expectation_contradicted": causal = "external_interference_possible"
    elif observation: causal = "independent_environment_observation"
    elif renderer_report: causal = "renderer_internal_only"
    else: causal = "causal_attribution_insufficient"
    effect_proven = bool(fulfillment_receipt and fulfillment_receipt.get("effect_proven") is True)
    proven = fulfillment_receipt.get("observed_consequence") if effect_proven and fulfillment_receipt else None
    comparison_base = {"schema_version":COMPARISON_SCHEMA,"expectation_id":expectation.expectation_id,
        "expectation_digest":expectation.expectation_digest,"observation_id":observation.observation_id if observation else None,
        "observation_digest":observation.observation_digest if observation else None,"observable_results":rows,"counts":counts,
        "universal_numeric_loss":None,"authority":dict(FALSE_AUTHORITY)}
    comparison_base["comparison_id"], comparison_base["comparison_digest"] = _identity("prediction-comparison", comparison_base)
    attribution_base = {"schema_version":ATTRIBUTION_SCHEMA,"expectation_id":expectation.expectation_id,
        "expectation_digest":expectation.expectation_digest,"handoff_id":handoff.get("handoff_id"),"handoff_digest":handoff.get("handoff_digest"),
        "renderer_report_id":renderer_report.report_id if renderer_report else None,"renderer_report_digest":renderer_report.report_digest if renderer_report else None,
        "observation_id":observation.observation_id if observation else None,"observation_digest":observation.observation_digest if observation else None,
        "comparison_id":comparison_base["comparison_id"],"comparison_digest":comparison_base["comparison_digest"],
        "body_generation":expectation.body_generation,"current_body_pointer_digest":current_body.get("pointer_digest"),
        "classification":classification,"causal_attribution_posture":causal,"commanded_value":dict(expectation.requested),
        "predicted_value":dict(expectation.predicted_observables),"renderer_reported_value":dict(renderer_report.applied) if renderer_report else None,
        "independently_observed_value":dict(observation.observed) if observation else None,"proven_consequence_value":proven,
        "effect_proven":effect_proven,"causal_principal_binding_digest":causal_principal_binding_digest,
        "measured_evidence":list(measured_evidence),"evaluated_at":evaluated_at,"authority":dict(FALSE_AUTHORITY)}
    attribution_base["attribution_id"], attribution_base["attribution_digest"] = _identity("consequence", attribution_base)
    return attribution_base, comparison_base


def world_state_records(*, expectation: EmbodiedActionExpectation, handoff: Mapping[str, Any],
                        renderer_report: AvatarRendererReport | None, observation: IndependentConsequenceObservation | None,
                        attribution: Mapping[str, Any], comparison: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = [{"source_kind":"embodiment","source_id":expectation.expectation_id,"schema_version":EXPECTATION_SCHEMA,
        "digest":expectation.expectation_digest,"subject_id":expectation.expectation_id,"subject_kind":"embodied_action_expectation",
        "stage":"proposal","disposition":"preregistered","observed_at":expectation.created_at,"effect_claimed":False,"effect_proven":False,"payload":asdict(expectation)},
        {"source_kind":"embodiment","source_id":str(handoff["handoff_id"]),"schema_version":str(handoff["schema_version"]),
         "digest":str(handoff["handoff_digest"]),"subject_id":str(handoff["handoff_id"]),"subject_kind":"avatar_renderer_handoff",
         "stage":"proposal","disposition":"commanded","effect_claimed":False,"effect_proven":False,"payload":dict(handoff)}]
    if renderer_report:
        records.append({"source_kind":"embodiment","source_id":renderer_report.report_id,"schema_version":REPORT_SCHEMA,"digest":renderer_report.report_digest,
            "subject_id":expectation.expectation_id,"subject_kind":"avatar_renderer_report","stage":"observation","disposition":renderer_report.renderer_status,
            "observed_at":renderer_report.completed_at,"effect_claimed":False,"effect_proven":False,"payload":asdict(renderer_report)})
    if observation:
        records.append({"source_kind":"embodiment","source_id":observation.observation_id,"schema_version":OBSERVATION_SCHEMA,"digest":observation.observation_digest,
            "subject_id":expectation.expectation_id,"subject_kind":"avatar_independently_observed_state","stage":"observation","disposition":"recorded",
            "observed_at":observation.observed_at,"effect_claimed":False,"effect_proven":False,"payload":asdict(observation)})
    for value, kind in ((attribution,"embodied_consequence_attribution"),(comparison,"embodied_prediction_comparison")):
        proven = bool(value.get("effect_proven", False))
        records.append({"source_kind":"fulfillment" if proven else "embodiment","source_id":value[f"{'attribution' if kind.endswith('attribution') else 'comparison'}_id"],
            "schema_version":value["schema_version"],"digest":value[f"{'attribution' if kind.endswith('attribution') else 'comparison'}_digest"],
            "subject_id":expectation.expectation_id,"subject_kind":kind,"stage":"execution" if proven else "observation",
            "disposition":value.get("classification","compared"),"observed_at":attribution["evaluated_at"],
            "effect_claimed":proven,"effect_proven":proven,"payload":dict(value)})
    return records


@dataclass(frozen=True)
class EmbodiedStrategyProposal:
    strategy_id: str
    strategy_digest: str
    situation_binding: str
    body_generation: int
    relevant_consequence_ids: tuple[str, ...]
    proposed_next_action_class: str
    requested_pose: str | None
    requested_expression: str | None
    retry_prior_strategy: bool
    alter_body_or_rig: bool
    more_observation_required: bool
    distinguishes_renderer_and_observer: bool
    rationale: str
    uncertainty: str
    factual_assertions: tuple[Mapping[str, Any], ...]
    authority: Mapping[str, bool]
    schema_version: str = STRATEGY_SCHEMA

    def semantic_payload(self) -> dict[str, Any]:
        value=asdict(self); value.pop("strategy_id"); value.pop("strategy_digest"); return value


def make_strategy_proposal(**kwargs: Any) -> EmbodiedStrategyProposal:
    raw=EmbodiedStrategyProposal("","",authority=dict(FALSE_AUTHORITY),**kwargs)
    verify_strategy_proposal(raw, identity_required=False)
    sid,dg=_identity("strategy",raw.semantic_payload()); return replace(raw,strategy_id=sid,strategy_digest=dg)


def verify_strategy_proposal(value: EmbodiedStrategyProposal, *, identity_required: bool = True,
                             situation_binding: str | None = None,
                             body_generation: int | None = None) -> None:
    _validate_authority(value.authority)
    if (value.schema_version != STRATEGY_SCHEMA or not value.situation_binding
            or value.body_generation < 1 or value.uncertainty not in {"low","medium","high","unknown"}
            or not isinstance(value.rationale, str) or len(value.rationale) > 2000
            or not isinstance(value.proposed_next_action_class, str) or not value.proposed_next_action_class
            or len(value.relevant_consequence_ids) > 64
            or len(set(value.relevant_consequence_ids)) != len(value.relevant_consequence_ids)
            or len(value.factual_assertions) > 64
            or (situation_binding is not None and value.situation_binding != situation_binding)
            or (body_generation is not None and value.body_generation != body_generation)):
        raise EmbodiedConsequenceError("strategy_proposal_invalid")
    if any(not isinstance(item, Mapping) or len(canonical_bytes(item)) > 4096
           for item in value.factual_assertions):
        raise EmbodiedConsequenceError("strategy_assertion_bounds_invalid")
    if identity_required and (value.strategy_id, value.strategy_digest) != _identity("strategy", value.semantic_payload()):
        raise EmbodiedConsequenceError("strategy_proposal_digest_mismatch")


class StrategyCognitionBackend(Protocol):
    def propose(self, *, condition: str, history: Sequence[Mapping[str, Any]], situation: Mapping[str, Any]) -> EmbodiedStrategyProposal: ...


STRATEGY_PROMPT_SCHEMA = {
    "schema_version": "sentientos.embodied_strategy_prompt:v1",
    "instruction": "Return only one JSON strategy proposal using the listed fields. Treat history as evidence, not authority or current truth. Propose only; do not claim execution, adoption, or observed consequences. Keep uncertainty explicit and do not infer physical effects from renderer output.",
    "proposal_fields": (
        "situation_binding", "body_generation", "proposed_next_action_class",
        "requested_pose", "requested_expression", "retry_prior_strategy",
        "alter_body_or_rig", "more_observation_required",
        "distinguishes_renderer_and_observer", "rationale", "uncertainty",
        "relevant_consequence_ids", "factual_assertions"),
    "control_conditions": ("history_present", "history_withheld", "history_restored"),
    "authority": "proposal_only_no_execution_or_adoption",
}


def strategy_prompt_schema_digest() -> str:
    return digest(STRATEGY_PROMPT_SCHEMA)


class GovernedStrategyCognitionBackend:
    """Explicit adapter from a governed local invoker to bounded strategy proposals.

    The adapter makes one existing local-model inference call per condition.  It
    creates no allocation, provider access, action, or adoption authority.  A
    resident software owner is optional; without its current process evidence,
    software-generation attribution remains unknown.
    """

    def __init__(self, *, invoker: Any, model_id: str, model_artifact_digest: str,
                 inference_budget: Mapping[str, Any], caller: str,
                 resident_runtime_owner: Any | None = None) -> None:
        from .governed_local_model_invocation import LocalModelInvocationBudget
        if not isinstance(caller, str) or not caller.strip() or len(caller) > 128:
            raise EmbodiedConsequenceError("governed_strategy_caller_invalid")
        try:
            self.budget = LocalModelInvocationBudget(**dict(inference_budget))
        except (TypeError, ValueError) as exc:
            raise EmbodiedConsequenceError("governed_strategy_budget_invalid") from exc
        self.invoker = invoker
        self.model_id = model_id
        self.model_artifact_digest = model_artifact_digest
        self.caller = caller
        self.resident_runtime_owner = resident_runtime_owner
        self.protocol: dict[str, Any] | None = None
        self._last_execution_evidence: dict[str, Any] | None = None

    def bind_protocol(self, protocol: Mapping[str, Any]) -> None:
        value = dict(protocol)
        if (value.get("prompt_schema_digest") != strategy_prompt_schema_digest()
                or value.get("inference_budget_digest") != digest(self.budget.to_dict())
                or value.get("model_id") != self.model_id
                or value.get("model_artifact_digest") != self.model_artifact_digest):
            raise EmbodiedConsequenceError("governed_strategy_protocol_binding_mismatch")
        if not isinstance(value.get("software_generation"), str) or not value["software_generation"]:
            raise EmbodiedConsequenceError("governed_strategy_software_generation_missing")
        self.protocol = value
        self._last_execution_evidence = None

    def _runtime_provenance(self) -> dict[str, Any] | None:
        if self.resident_runtime_owner is None:
            return None
        observe = getattr(self.resident_runtime_owner, "current_execution_provenance", None)
        if not callable(observe):
            return None
        try:
            value = observe()
        except (OSError, RuntimeError, ValueError, TypeError):
            return None
        if not isinstance(value, Mapping):
            raise EmbodiedConsequenceError("resident_execution_provenance_invalid")
        return dict(value)

    def propose(self, *, condition: str, history: Sequence[Mapping[str, Any]],
                situation: Mapping[str, Any]) -> EmbodiedStrategyProposal:
        from .governed_local_model_invocation import validate_receipt
        from .local_model_authority import digest_payload
        if self.protocol is None:
            raise EmbodiedConsequenceError("governed_strategy_protocol_unbound")
        if condition not in ("history_present", "history_withheld", "history_restored"):
            raise EmbodiedConsequenceError("governed_strategy_condition_invalid")
        context = {"schema": STRATEGY_PROMPT_SCHEMA, "condition": condition,
            "history": [dict(item) for item in history], "situation": dict(situation)}
        prompt = canonical_bytes(context).decode("utf-8")
        runtime_before = self._runtime_provenance()
        correlation = "strategy-experiment:" + digest({"protocol": self.protocol["protocol_digest"],
            "condition": condition})[7:]
        request = self.invoker.build_request(purpose="resident_developmental_history_intervention_experiment",
            prompt=prompt, caller=self.caller, correlation_id=correlation, lifecycle_phase="runtime",
            expected_output_format="json", budget=self.budget,
            upstream_evidence={"experiment_protocol_digest": self.protocol["protocol_digest"]},
            linkage={"experiment_condition": condition,
                "experiment_protocol_id": self.protocol["protocol_id"],
                "history_record_ids": [str(item.get("record_id", "")) for item in history]})
        receipt = self.invoker.invoke(request, persist=True, include_output_in_receipt=False)
        receipt_value = receipt.to_dict(include_output=False)
        self._last_execution_evidence = {"condition": condition,
            "execution_posture": "incomplete_invocation_receipt",
            "receipt_id": receipt_value.get("receipt_id"),
            "receipt_digest": receipt_value.get("receipt_digest"),
            "invocation_receipt": receipt_value}
        runtime_after = self._runtime_provenance()
        if runtime_before is not None and runtime_after is not None and runtime_before != runtime_after:
            software_posture = "contradictory_process_identity_changed_during_inference"
        elif runtime_after is None:
            software_posture = ("incomplete_resident_execution_provenance" if self.resident_runtime_owner is not None
                else "unknown_no_resident_execution_owner")
        elif runtime_after.get("represented_generation_digest") != self.protocol["software_generation"]:
            software_posture = "contradictory_protocol_generation_mismatch"
        else:
            software_posture = "verified_current_resident_generation"

        output = getattr(receipt, "output_text", None)
        if (not isinstance(output, str) or not output or getattr(receipt, "status", None) != "admitted_completed"
                or getattr(receipt, "output_truncated", True)
                or dict(getattr(receipt, "effects", {})).get("local_model_inference") is not True):
            raise EmbodiedConsequenceError("governed_strategy_invocation_incomplete")
        valid, findings = validate_receipt(receipt_value)
        if not valid:
            raise EmbodiedConsequenceError("governed_strategy_receipt_invalid:" + ",".join(findings))
        req = receipt_value.get("request")
        if not isinstance(req, Mapping):
            raise EmbodiedConsequenceError("governed_strategy_request_missing")
        request_semantic = {key: value for key, value in req.items()
            if key not in {"request_id", "request_digest", "raw_prompt_stored", "ephemeral_prompt_handling"}}
        request_digest = digest_payload(request_semantic)
        active_identity = req.get("active_model_identity")
        if (req.get("request_digest") != request_digest
                or req.get("request_id") != "lmreq-" + request_digest[:24]
                or req.get("purpose") != "resident_developmental_history_intervention_experiment"
                or req.get("prompt_digest") != digest_payload({"prompt": prompt})
                or req.get("model_id") != self.model_id
                or req.get("model_artifact_digest") != self.model_artifact_digest
                or req.get("budget") != self.budget.to_dict()
                or not isinstance(active_identity, Mapping)
                or active_identity.get("model_content_sha256") != self.model_artifact_digest
                or active_identity.get("posture") != "production"
                or active_identity.get("fallback") is not False):
            raise EmbodiedConsequenceError("governed_strategy_execution_identity_mismatch")
        response_digest = digest_payload({"output": output})
        if receipt_value.get("output_digest") != response_digest:
            raise EmbodiedConsequenceError("governed_strategy_response_binding_mismatch")
        try:
            proposal_payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise EmbodiedConsequenceError("governed_strategy_response_not_json") from exc
        if not isinstance(proposal_payload, Mapping):
            raise EmbodiedConsequenceError("governed_strategy_response_shape_invalid")
        fields = set(EmbodiedStrategyProposal.__dataclass_fields__) - {
            "strategy_id", "strategy_digest", "authority", "schema_version"}
        if set(proposal_payload) != fields:
            raise EmbodiedConsequenceError("governed_strategy_response_fields_invalid")
        semantic = dict(proposal_payload)
        for name in ("relevant_consequence_ids", "factual_assertions"):
            if not isinstance(semantic.get(name), list):
                raise EmbodiedConsequenceError("governed_strategy_response_fields_invalid")
            semantic[name] = tuple(semantic[name])
        proposal = make_strategy_proposal(**semantic)
        verify_strategy_proposal(proposal, situation_binding=str(situation.get("situation_binding", "")),
            body_generation=int(self.protocol["body_generation"]))
        serving_identity = req.get("linkage", {}).get("resident_cognitive_serving") if isinstance(req.get("linkage"), Mapping) else None
        serving_identity_posture = ("verified_session_bound" if isinstance(serving_identity, Mapping)
            and all(serving_identity.get(key) for key in ("session_id", "model_serving_admission_ref",
                "activation_state_semantic_digest")) else "unknown_no_resident_serving_session")
        evidence = {"condition": condition, "request_id": req["request_id"],
            "request_digest": request_digest, "prompt_digest": req["prompt_digest"],
            "history_digest": digest(context["history"]), "situation_digest": digest(dict(situation)),
            "model_id": req["model_id"], "model_artifact_digest": req["model_artifact_digest"],
            "active_model_identity": dict(active_identity),
            "active_model_identity_digest": digest(dict(active_identity)),
            "authority_map_digest": req.get("authority_map_digest"),
            "serving_identity": dict(serving_identity) if isinstance(serving_identity, Mapping) else None,
            "serving_identity_posture": serving_identity_posture,
            "receipt_id": receipt_value.get("receipt_id"), "receipt_digest": receipt_value.get("receipt_digest"),
            "invocation_receipt": receipt_value,
            "response_digest": response_digest,
            "proposal_id": proposal.strategy_id, "proposal_digest": proposal.strategy_digest,
            "software_generation_posture": software_posture,
            "software_execution_provenance": runtime_after,
            "execution_posture": "verified_governed_model_identity"}
        evidence["association_digest"] = digest(evidence)
        self._last_execution_evidence = evidence
        return proposal

    def consume_execution_evidence(self) -> dict[str, Any] | None:
        result, self._last_execution_evidence = self._last_execution_evidence, None
        return result


def score_strategy_experiment(*, proposals: Sequence[EmbodiedStrategyProposal], consequence: Mapping[str, Any]) -> dict[str, Any]:
    if len(proposals)!=3: raise EmbodiedConsequenceError("strategy_condition_count_invalid")
    _verify_consequence_attribution(consequence)
    for proposal in proposals: verify_strategy_proposal(proposal)
    present,withheld,restored=proposals
    known={str(consequence["attribution_id"])}
    def score(p: EmbodiedStrategyProposal) -> dict[str, Any]:
        cited=set(p.relevant_consequence_ids); unsupported=[dict(x) for x in p.factual_assertions if x.get("source_id") not in known]
        contradicted=consequence["classification"]=="expectation_contradicted"
        return {"strategy_id":p.strategy_id,"prior_consequence_cited_correctly":bool(cited) and cited<=known,
            "unsupported_factual_assertions":unsupported,"repeats_previously_contradicted_action":contradicted and p.retry_prior_strategy,
            "requests_more_evidence_under_unresolved_attribution":p.more_observation_required if consequence["causal_attribution_posture"] in {"external_interference_possible","causal_attribution_insufficient"} else None,
            "distinguishes_renderer_report_from_independent_observation":p.distinguishes_renderer_and_observer,
            "unsupported_body_modification":p.alter_body_or_rig and not bool(cited),"provenance_correct":cited<=known,
            "abstention":p.proposed_next_action_class=="abstain"}
    structural=(present.semantic_payload()==withheld.semantic_payload(),present.semantic_payload()==restored.semantic_payload())
    rows=[score(p) for p in proposals]
    if any(r["unsupported_factual_assertions"] or r["unsupported_body_modification"] for r in rows): outcome="unsupported"
    elif not structural[1]: outcome="unstable"
    elif structural[0]: outcome="unchanged"
    else: outcome="changed"
    payload={"proposal_structural_equalities":{"present_equals_withheld":structural[0],"present_equals_restored":structural[1]},
        "proposal_scores":rows,"outcome":outcome,"improvement_claimed":False,"authority":dict(FALSE_AUTHORITY)}
    payload["score_digest"]=digest(payload); return payload


def run_strategy_experiment(*, protocol: Mapping[str, Any], history_record: Mapping[str, Any], situation: Mapping[str, Any],
                            backend: StrategyCognitionBackend, consequence: Mapping[str, Any]) -> dict[str, Any]:
    required={"protocol_id","snapshot_digest","body_generation","model_id","model_artifact_digest","inference_budget_digest",
              "prompt_schema_digest","renderer_situation_digest","software_generation","environment_fixture_digest"}
    if (set(protocol)!=required or len(canonical_bytes(dict(protocol)))>MAX_STRATEGY_CONTEXT_BYTES
            or any(not isinstance(protocol.get(key),str) or not protocol[key]
                   for key in required-{"body_generation"})
            or type(protocol.get("body_generation")) is not int or protocol["body_generation"]<1
            or len(canonical_bytes(dict(history_record)))>MAX_STRATEGY_CONTEXT_BYTES
            or len(canonical_bytes(dict(situation)))>MAX_STRATEGY_CONTEXT_BYTES):
        raise EmbodiedConsequenceError("strategy_protocol_shape_invalid")
    _verify_consequence_attribution(consequence)
    record_digest=history_record.get("record_digest")
    record_semantic=dict(history_record); record_semantic.pop("record_id",None); record_semantic.pop("record_digest",None)
    calculated_record_digest=digest(record_semantic)
    calculated_record_id="devrec-"+calculated_record_digest[7:31]
    history_binding_verified=(record_digest==calculated_record_digest
                              and history_record.get("record_id")==calculated_record_id
                              and isinstance(history_record.get("candidate"),Mapping)
                              and history_record["candidate"].get("epistemic_posture")=="historical_interpretation_not_current_truth"
                              and history_record.get("current_truth") is False
                              and history_record.get("authority") is False
                              and history_record.get("policy") is False)
    situation_digest=digest(dict(situation))
    situation_binding_verified=protocol.get("renderer_situation_digest")==situation_digest
    evidence_scope=_history_evidence_scope(history_record)
    conditions=("history_present","history_withheld","history_restored")
    protocol_id, protocol_digest = _identity("strategy-protocol", dict(protocol))
    bind_protocol = getattr(backend, "bind_protocol", None)
    if callable(bind_protocol):
        bind_protocol({**dict(protocol), "protocol_id": protocol_id, "protocol_digest": protocol_digest})
    proposals=[]
    execution_evidence=[]
    condition_statuses=[]
    failure_posture=None
    execution_contradiction=False
    for condition in conditions:
        history=() if condition=="history_withheld" else (history_record,)
        # Each call receives an independent canonical copy so a backend cannot
        # mutate shared context and contaminate a later control condition.
        situation_copy=json.loads(canonical_bytes(dict(situation)))
        take_evidence = getattr(backend, "consume_execution_evidence", None)
        evidence = None
        try:
            proposal = backend.propose(condition=condition,history=history,situation=situation_copy)
            evidence = take_evidence() if callable(take_evidence) else None
            if evidence is not None:
                if not isinstance(backend, GovernedStrategyCognitionBackend) or not isinstance(evidence, Mapping):
                    raise EmbodiedConsequenceError("unowned_governed_execution_evidence")
                row = dict(evidence)
                row_digest = row.pop("association_digest", None)
                receipt = row.get("invocation_receipt")
                from .governed_local_model_invocation import validate_receipt
                from .local_model_authority import digest_payload
                valid_receipt, _ = validate_receipt(receipt) if isinstance(receipt, Mapping) else (False, ["missing_receipt"])
                receipt_request = receipt.get("request") if isinstance(receipt, Mapping) else None
                expected_prompt = canonical_bytes({"schema": STRATEGY_PROMPT_SCHEMA,
                    "condition": condition, "history": [dict(item) for item in history],
                    "situation": situation_copy}).decode("utf-8")
                linkage = receipt_request.get("linkage") if isinstance(receipt_request, Mapping) else None
                if (row_digest != digest(row) or not valid_receipt
                        or row.get("condition") != condition
                        or row.get("proposal_id") != proposal.strategy_id
                    or row.get("proposal_digest") != proposal.strategy_digest
                    or not isinstance(receipt_request, Mapping)
                    or receipt.get("receipt_id") != row.get("receipt_id")
                    or receipt.get("receipt_digest") != row.get("receipt_digest")
                    or receipt_request.get("request_id") != row.get("request_id")
                    or receipt_request.get("request_digest") != row.get("request_digest")
                    or receipt_request.get("prompt_digest") != digest_payload({"prompt": expected_prompt})
                    or receipt_request.get("purpose") != "resident_developmental_history_intervention_experiment"
                    or receipt_request.get("model_id") != protocol.get("model_id")
                    or receipt_request.get("model_artifact_digest") != protocol.get("model_artifact_digest")
                    or digest(receipt_request.get("budget")) != protocol.get("inference_budget_digest")
                    or receipt_request.get("active_model_identity") != row.get("active_model_identity")
                    or receipt_request.get("authority_map_digest") != row.get("authority_map_digest")
                    or receipt.get("output_digest") != row.get("response_digest")
                    or row.get("response_digest") != receipt.get("output_digest")
                    or receipt.get("status") != "admitted_completed"
                    or receipt.get("output_truncated") is not False
                    or receipt.get("fallback_occurred") is not False
                    or not isinstance(receipt.get("effects"), Mapping)
                    or receipt["effects"].get("local_model_inference") is not True
                    or row.get("active_model_identity_digest") != digest(row.get("active_model_identity"))
                    or not isinstance(linkage, Mapping)
                    or linkage.get("experiment_condition") != condition
                    or linkage.get("experiment_protocol_id") != protocol_id
                    or linkage.get("history_record_ids") != [str(item.get("record_id", "")) for item in history]):
                    raise EmbodiedConsequenceError("governed_execution_evidence_binding_invalid")
                row["association_digest"] = row_digest
                execution_evidence.append(row)
            else:
                execution_evidence.append({"condition": condition, "execution_posture": "unknown_no_governed_receipt"})
            proposals.append(proposal)
            condition_statuses.append({"condition": condition, "status": "completed",
                "proposal_id": proposal.strategy_id, "proposal_digest": proposal.strategy_digest})
        except Exception as exc:
            if evidence is None and callable(take_evidence):
                evidence = take_evidence()
            if isinstance(evidence, Mapping):
                receipt = evidence.get("invocation_receipt")
                if isinstance(receipt, Mapping):
                    from .governed_local_model_invocation import validate_receipt
                    receipt_valid, _ = validate_receipt(receipt)
                    execution_evidence.append({"condition": condition,
                        "execution_posture": "incomplete_invocation_receipt",
                        "receipt_id": receipt.get("receipt_id"), "receipt_digest": receipt.get("receipt_digest"),
                        "receipt_valid": receipt_valid, "invocation_receipt": dict(receipt)})
                else:
                    execution_evidence.append({"condition": condition,
                        "execution_posture": "incomplete_or_contradictory_evidence",
                        "evidence_digest": digest(dict(evidence))})
            failure_posture = getattr(exc, "code", None) or "backend_failure:" + type(exc).__name__
            failure_text = str(failure_posture).lower()
            contradictory = any(marker in failure_text for marker in
                ("mismatch", "invalid", "contradictory", "malformed", "binding", "digest", "fields", "shape"))
            execution_contradiction = execution_contradiction or contradictory
            condition_statuses.append({"condition": condition, "status": "contradictory" if contradictory else "incomplete",
                "failure_posture": str(failure_posture)[:128]})
            break
    expected_situation_binding=str(situation.get("situation_binding", ""))
    proposal_contradiction = False
    for proposal in proposals:
        try:
            verify_strategy_proposal(proposal, situation_binding=expected_situation_binding,
                                     body_generation=int(protocol["body_generation"]))
        except (EmbodiedConsequenceError, TypeError, ValueError):
            proposal_contradiction = True
            failure_posture = "proposal_identity_or_context_contradictory"
            for status in condition_statuses:
                if status.get("proposal_id") == getattr(proposal, "strategy_id", None):
                    status["status"] = "contradictory"
                    status["failure_posture"] = failure_posture
            break
    experiment_contradictory = proposal_contradiction or execution_contradiction
    experiment_complete = len(proposals) == len(conditions) and not experiment_contradictory
    scoring=(score_strategy_experiment(proposals=proposals,consequence=consequence)
        if experiment_complete else {"status":"not_scored_incomplete_execution", "authority":dict(FALSE_AUTHORITY)})
    governed_rows = [item for item in execution_evidence if item.get("execution_posture") == "verified_governed_model_identity"]
    if experiment_contradictory:
        execution_posture = "contradictory_strategy_proposal"
    elif not experiment_complete:
        execution_posture = "incomplete_interrupted_before_all_conditions"
    elif not governed_rows:
        execution_posture = "declared_only_no_invocation_receipt"
    elif len(governed_rows) != len(conditions):
        execution_posture = "partial_governed_invocation_evidence"
    elif any(item.get("model_id") != protocol.get("model_id")
             or item.get("model_artifact_digest") != protocol.get("model_artifact_digest")
             for item in governed_rows):
        execution_posture = "contradictory_model_identity"
    elif len({item.get("active_model_identity_digest") for item in governed_rows}) != 1:
        execution_posture = "contradictory_model_identity_changed_across_conditions"
    elif len({item.get("authority_map_digest") for item in governed_rows}) != 1:
        execution_posture = "contradictory_authority_map_changed_across_conditions"
    elif len({digest(item.get("invocation_receipt", {}).get("generation_config"))
              for item in governed_rows}) != 1:
        execution_posture = "contradictory_generation_parameters_changed_across_conditions"
    elif any(str(item.get("software_generation_posture", "")).startswith("contradictory")
             for item in governed_rows):
        execution_posture = "verified_model_but_contradictory_software_generation"
    elif all(item.get("software_generation_posture") == "verified_current_resident_generation"
             and item.get("serving_identity_posture") == "verified_session_bound"
             for item in governed_rows):
        if len({digest(item.get("serving_identity")) for item in governed_rows}) == 1:
            execution_posture = "verified_governed_model_serving_and_running_software_generation"
        else:
            execution_posture = "contradictory_serving_identity_changed_across_conditions"
    else:
        execution_posture = "verified_model_identity_serving_or_software_identity_unknown_or_incomplete"
    execution_context_stable = (len(governed_rows) == len(conditions)
        and len({item.get("active_model_identity_digest") for item in governed_rows}) == 1
        and all(item.get("software_generation_posture") == "verified_current_resident_generation"
                and item.get("serving_identity_posture") == "verified_session_bound"
                and isinstance(item.get("software_execution_provenance"), Mapping)
                for item in governed_rows)
        and len({digest(item.get("software_execution_provenance")) for item in governed_rows}) == 1
        and len({item.get("authority_map_digest") for item in governed_rows}) == 1
        and len({digest(item.get("invocation_receipt", {}).get("generation_config"))
                 for item in governed_rows}) == 1
        and len({digest(item.get("serving_identity")) for item in governed_rows}) == 1)
    if experiment_contradictory:
        validity = "proposal_identity_contradictory"
    elif not experiment_complete:
        validity = "execution_incomplete"
    elif not history_binding_verified or not situation_binding_verified:
        validity = "context_binding_incomplete"
    elif execution_posture == "verified_governed_model_serving_and_running_software_generation":
        validity = "controlled_context_identity_consistent"
    elif execution_posture.startswith("contradictory") or "contradictory" in execution_posture:
        validity = "execution_identity_contradictory"
    else:
        validity = "input_context_consistent_execution_identity_unknown_or_incomplete"
    payload={"schema_version":EXPERIMENT_RESULT_SCHEMA,"protocol":dict(protocol),"protocol_digest":digest(protocol),
        "condition_order":list(conditions),"withheld_record_id":history_record.get("record_id"),"withheld_record_digest":record_digest,
        "condition_statuses":condition_statuses,
        "experiment_completion_posture":"contradictory" if experiment_contradictory else "completed" if experiment_complete else "incomplete",
        "failure_posture":failure_posture,
        "history_record_identity_consistent":history_binding_verified,
        "situation_matches_declared_digest":situation_binding_verified,
        "cognitive_execution_identity_posture":execution_posture,
        "execution_context_stable_across_conditions":execution_context_stable if callable(bind_protocol) else None,
        "execution_evidence":execution_evidence,
        "consequence_scope":"prior_context_only_no_post_experiment_consequence_observed",
        "input_context_digest":digest({"situation":dict(situation),"history_record_id":history_record.get("record_id"),
            "history_record_digest":record_digest,"consequence_id":consequence.get("attribution_id"),
            "consequence_digest":consequence.get("attribution_digest")}),
        "evidence_scope":evidence_scope,
        "validity":validity,
        "proposals":[asdict(p) for p in proposals],"scoring":scoring,"no_retries":True,"improvement_claimed":False,"authority":dict(FALSE_AUTHORITY)}
    payload["experiment_result_id"],payload["experiment_result_digest"]=_identity("strategy-experiment",payload)
    return payload


def _verify_consequence_attribution(value: Mapping[str, Any]) -> None:
    semantic=dict(value); claimed_id=semantic.pop("attribution_id",None); claimed_digest=semantic.pop("attribution_digest",None)
    expected_id,expected_digest=_identity("consequence",semantic)
    if claimed_id!=expected_id or claimed_digest!=expected_digest or dict(value.get("authority",{}))!=dict(FALSE_AUTHORITY):
        raise EmbodiedConsequenceError("consequence_attribution_binding_invalid")


def _history_evidence_scope(record: Mapping[str, Any]) -> dict[str, Any]:
    candidate=record.get("candidate")
    if not isinstance(candidate,Mapping):
        return {"posture":"incomplete_record_candidate","resource_fact_count":0,"resource_bindings":[]}
    fact_ids=tuple(candidate.get("selected_fact_ids",()))
    facts=tuple(candidate.get("selected_facts",()))
    if (not facts or len(facts)>16 or len(facts)!=len(fact_ids)
            or tuple(str(item.get("fact_id","")) for item in facts if isinstance(item,Mapping))!=fact_ids):
        return {"posture":"selected_fact_identity_incomplete","resource_fact_count":0,"resource_bindings":[]}
    resource_facts=[]; verified=True
    for fact in facts:
        if not isinstance(fact,Mapping):
            verified=False; continue
        source=fact.get("source"); subject=fact.get("subject"); payload=fact.get("payload")
        if not isinstance(source,Mapping) or not isinstance(subject,Mapping) or not isinstance(payload,Mapping):
            verified=False; continue
        if source.get("kind")!="resource_governor" or subject.get("subject_kind")!="causal_resource_consumption":
            continue
        allocation_values=payload.get("allocations",())
        attempt_values=payload.get("attempts",())
        receipt_values=payload.get("consumption_receipts",())
        invocation_values=payload.get("invocation_receipts",())
        if not all(isinstance(value,(tuple,list)) for value in
                   (allocation_values,attempt_values,receipt_values,invocation_values)):
            verified=False; continue
        binding={"fact_id":fact.get("fact_id"),"source_id":source.get("source_id"),
            "source_digest":source.get("digest"),"ledger_digest":payload.get("ledger_digest"),
            "allocation_digests":tuple(str(item.get("allocation_digest","")) for item in allocation_values if isinstance(item,Mapping)),
            "attempt_ids":tuple(str(item.get("attempt_id","")) for item in attempt_values if isinstance(item,Mapping)),
            "consumption_receipts":tuple((str(item.get("receipt_id","")),str(item.get("receipt_digest","")))
                for item in receipt_values if isinstance(item,Mapping)),
            "invocation_receipts":tuple((str(item.get("receipt_id","")),str(item.get("receipt_digest","")))
                for item in invocation_values if isinstance(item,Mapping)),
            "lineage_posture":payload.get("lineage_posture"),"recovery_posture":payload.get("recovery_posture"),
            "measurement_attribution":payload.get("shared_host_usage_attribution")}
        resource_facts.append(binding)
        if (binding["lineage_posture"]!="verified" or binding["recovery_posture"]!="reconciled_or_restored"
                or payload.get("retention_posture")!="complete"
                or payload.get("interpretation_projection_posture")!="complete"
                or not binding["source_digest"] or not binding["ledger_digest"]):
            verified=False
    if not resource_facts:
        posture="no_resource_evidence_in_selected_record"
    elif not verified:
        posture="resource_evidence_lineage_incomplete"
    elif len(resource_facts)!=len(facts):
        posture="mixed_selected_history"
    else:
        posture="resource_only_receipt_bound_history"
    return {"posture":posture,"selected_fact_ids":fact_ids,
        "selected_fact_count":len(facts),"resource_fact_count":len(resource_facts),
        "resource_bindings":resource_facts}


class ConsequenceStore:
    """Immutable exact-chain store for consequence and experiment artifacts."""
    def __init__(self, root: Path) -> None:
        selected=Path(root)
        if selected.is_symlink(): raise EmbodiedConsequenceError("consequence_store_root_symlink")
        selected.mkdir(parents=True,exist_ok=True,mode=0o700)
        if selected.is_symlink() or not selected.is_dir(): raise EmbodiedConsequenceError("consequence_store_root_invalid")
        self.root=selected.resolve()

    def _path(self, kind: str, identity: str) -> Path:
        if kind not in _CONSEQUENCE_KINDS or not isinstance(identity,str) or not _CONSEQUENCE_ID.fullmatch(identity):
            raise EmbodiedConsequenceError("consequence_artifact_selector_invalid")
        directory=self.root/kind
        try: os.mkdir(directory,0o700)
        except FileExistsError: pass
        try: metadata=directory.lstat()
        except OSError as exc: raise EmbodiedConsequenceError("consequence_artifact_directory_invalid") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise EmbodiedConsequenceError("consequence_artifact_directory_invalid")
        return directory/f"{identity}.json"

    @staticmethod
    def _read(path: Path) -> bytes:
        flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)
        try: descriptor=os.open(path,flags)
        except OSError as exc: raise EmbodiedConsequenceError("stored_artifact_missing_or_unsafe") from exc
        try:
            metadata=os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size>MAX_CONSEQUENCE_ARTIFACT_BYTES:
                raise EmbodiedConsequenceError("stored_artifact_unbounded_or_not_regular")
            chunks=[]; remaining=MAX_CONSEQUENCE_ARTIFACT_BYTES+1
            while remaining:
                chunk=os.read(descriptor,min(65536,remaining))
                if not chunk: break
                chunks.append(chunk); remaining-=len(chunk)
            data=b"".join(chunks)
            if len(data)>MAX_CONSEQUENCE_ARTIFACT_BYTES:
                raise EmbodiedConsequenceError("stored_artifact_unbounded_or_not_regular")
            return data
        finally: os.close(descriptor)

    def put(self, kind: str, identity: str, value: Mapping[str, Any]) -> Path:
        path=self._path(kind,identity)
        id_field,digest_field,prefix=_ARTIFACT_IDENTITIES[kind]
        semantic=dict(value); claimed_id=semantic.pop(id_field,None); claimed_digest=semantic.pop(digest_field,None)
        expected_id,expected_digest=_identity(prefix,semantic)
        if claimed_id!=identity or claimed_id!=expected_id or claimed_digest!=expected_digest:
            raise EmbodiedConsequenceError("artifact_identity_or_digest_invalid")
        data=canonical_bytes(value)+b"\n"
        if len(data)>MAX_CONSEQUENCE_ARTIFACT_BYTES: raise EmbodiedConsequenceError("artifact_size_bound_exceeded")
        fd,temp=tempfile.mkstemp(dir=path.parent,prefix=".consequence-")
        try:
            with os.fdopen(fd,"wb") as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())
            try: os.link(temp,path)
            except FileExistsError:
                if self._read(path)!=data: raise EmbodiedConsequenceError("artifact_identity_collision")
            try:
                directory_fd=os.open(path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
                try: os.fsync(directory_fd)
                finally: os.close(directory_fd)
            except OSError: pass
        finally:
            if os.path.exists(temp): os.unlink(temp)
        return path
    def get(self, kind: str, identity: str, *, digest_field: str) -> dict[str, Any]:
        path=self._path(kind,identity)
        id_field,expected_digest_field,prefix=_ARTIFACT_IDENTITIES[kind]
        if digest_field!=expected_digest_field: raise EmbodiedConsequenceError("artifact_digest_selector_invalid")
        try: value=json.loads(self._read(path).decode("utf-8"))
        except (UnicodeError,json.JSONDecodeError) as exc: raise EmbodiedConsequenceError("stored_artifact_missing_or_corrupt") from exc
        if not isinstance(value,dict): raise EmbodiedConsequenceError("stored_artifact_shape_invalid")
        claimed=value.get(digest_field); semantic=dict(value); semantic.pop(digest_field,None); claimed_id=semantic.pop(id_field,None)
        calculated_id,calculated_digest=_identity(prefix,semantic)
        if (claimed!=calculated_digest or claimed_id!=identity or calculated_id!=identity):
            raise EmbodiedConsequenceError("stored_artifact_digest_mismatch_or_identity_invalid")
        return cast(dict[str, Any], value)
