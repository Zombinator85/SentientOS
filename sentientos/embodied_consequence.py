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
import secrets
import stat
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, cast
from .windows_handle_custody import WindowsHandleCustodyError, read_regular_files

try:
    import fcntl as _fcntl
except ImportError:  # Windows hosted development has no POSIX fcntl module.
    _fcntl = None

EXPECTATION_SCHEMA = "sentientos.embodied_action_expectation:v1"
HANDOFF_SCHEMA = "sentientos.avatar_renderer_handoff:v1"
REPORT_SCHEMA = "sentientos.avatar_renderer_report:v1"
OBSERVATION_SCHEMA = "sentientos.avatar_independent_observation:v1"
ATTRIBUTION_SCHEMA = "sentientos.embodied_consequence_attribution:v1"
COMPARISON_SCHEMA = "sentientos.embodied_prediction_comparison:v1"
STRATEGY_SCHEMA = "sentientos.embodied_strategy_proposal:v1"
EXPERIMENT_SCHEMA = "sentientos.embodied_strategy_experiment:v1"
LEGACY_EXPERIMENT_RESULT_SCHEMA = "sentientos.embodied_strategy_experiment_result:v1"
EXPERIMENT_RESULT_SCHEMA = "sentientos.embodied_strategy_experiment_result:v2"
STRATEGY_CONDITION_START_SCHEMA = "sentientos.embodied_strategy_condition_start:v1"
STRATEGY_CONDITION_RESULT_SCHEMA = "sentientos.embodied_strategy_condition_result:v1"
CONSEQUENCE_CHAIN_SCHEMA = "sentientos.embodied_consequence_chain:v1"
WORLD_STATE_PROJECTION_CONFIG_SCHEMA = "sentientos.embodied_consequence_world_state_projection_config:v1"
WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V2 = "sentientos.embodied_consequence_world_state_projection_config:v2"
WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V3 = "sentientos.embodied_consequence_world_state_projection_config:v3"
MAX_STRATEGY_CONTEXT_BYTES = 1_048_576
MAX_CONSEQUENCE_ARTIFACT_BYTES = 2_097_152
MAX_CONSEQUENCE_ARTIFACTS_PER_KIND = 4096
MAX_WORLD_STATE_PROJECTION_RECORDS = 48
MAX_WORLD_STATE_PROJECTION_RECORD_BYTES = 32_768
_CONSEQUENCE_KINDS = {"expectations", "reports", "observations", "attributions", "comparisons",
    "strategy-experiments", "strategy-experiment-starts", "strategy-experiment-conditions",
    "consequence-chains"}
_CONSEQUENCE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}:[0-9a-f]{24}\Z")
_ARTIFACT_IDENTITIES = {
    "expectations": ("expectation_id", "expectation_digest", "expectation"),
    "reports": ("report_id", "report_digest", "renderer-report"),
    "observations": ("observation_id", "observation_digest", "independent-observation"),
    "attributions": ("attribution_id", "attribution_digest", "consequence"),
    "comparisons": ("comparison_id", "comparison_digest", "prediction-comparison"),
    "strategy-experiments": ("experiment_result_id", "experiment_result_digest", "strategy-experiment"),
    "consequence-chains": ("chain_id", "chain_digest", "consequence-chain"),
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


def verify_renderer_handoff(value: Mapping[str, Any]) -> None:
    fields = {"schema_version", "body_generation", "artifact_sha256", "body_manifest_digest",
        "renderer_interface_id", "requested_test_pose", "requested_test_expression", "correlation_id",
        "commanded_at", "evidence_class", "renderer_reported", "independently_observed", "authority",
        "handoff_id", "handoff_digest"}
    if (set(value) != fields or value.get("schema_version") != HANDOFF_SCHEMA
            or type(value.get("body_generation")) is not int or value["body_generation"] < 1
            or value.get("evidence_class") != "commanded_output"
            or value.get("renderer_reported") is not False
            or value.get("independently_observed") is not False
            or dict(value.get("authority") or {}) != dict(FALSE_AUTHORITY)
            or any(not isinstance(value.get(key), str) or not value.get(key) for key in (
                "artifact_sha256", "body_manifest_digest", "renderer_interface_id",
                "requested_test_pose", "requested_test_expression", "correlation_id"))):
        raise EmbodiedConsequenceError("renderer_handoff_shape_invalid")
    if value.get("commanded_at") is not None:
        _time(value["commanded_at"])
    semantic = {key: item for key, item in value.items() if key not in {"handoff_id", "handoff_digest"}}
    expected_id = "handoff:" + digest(semantic)[7:31]
    expected_digest = digest({key: item for key, item in value.items() if key != "handoff_digest"})
    if value.get("handoff_id") != expected_id or value.get("handoff_digest") != expected_digest:
        raise EmbodiedConsequenceError("renderer_handoff_digest_mismatch")


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
                         measured_evidence: Sequence[Mapping[str, Any]] = (), evaluated_at: str,
                         consequence_store: Any | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    verify_expectation(expectation)
    handoff_integrity_valid = True
    try:
        verify_renderer_handoff(handoff)
    except EmbodiedConsequenceError:
        # Preserve typed mismatch outcomes for tampered handoffs; the record
        # remains unfit for World-State publication until its full lineage is valid.
        handoff_integrity_valid = False
    if renderer_report: verify_renderer_report(renderer_report)
    if observation: verify_independent_observation(observation)
    if fulfillment_receipt and fulfillment_receipt.get("effect_proven") is True:
        raise EmbodiedConsequenceError("unverified_fulfillment_receipt_cannot_prove_effect")
    now = _time(evaluated_at)
    mismatch = False
    required = (expectation.handoff_id == handoff.get("handoff_id"), expectation.handoff_digest == handoff.get("handoff_digest"),
        expectation.correlation_id == handoff.get("correlation_id"), expectation.body_manifest_digest == handoff.get("body_manifest_digest"))
    mismatch = not all(required) or not handoff_integrity_valid
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
    # The observation contract currently binds a source string and digest but
    # no authenticated observer issuer. Preserve the claim as evidence while
    # refusing to promote that caller-supplied label into independent causal
    # attribution.
    if observation and classification == "expectation_contradicted": causal = "external_interference_possible"
    elif renderer_report: causal = "renderer_internal_only"
    else: causal = "causal_attribution_insufficient"
    # No independently authoritative physical-effect receipt owner is composed
    # here. A descriptive fulfillment row cannot establish an actual effect.
    effect_proven = False
    proven = None
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
        "independently_observed_value":dict(observation.observed) if observation else None,
        "observation_independence_posture": "unverified_caller_assertion" if observation else "no_observation",
        "proven_consequence_value":proven,
        "effect_proven":effect_proven,"causal_principal_binding_digest":causal_principal_binding_digest,
        "measured_evidence":list(measured_evidence),"evaluated_at":evaluated_at,"authority":dict(FALSE_AUTHORITY)}
    attribution_base["attribution_id"], attribution_base["attribution_digest"] = _identity("consequence", attribution_base)
    if consequence_store is not None:
        persist_chain = getattr(consequence_store, "put_consequence_chain", None)
        if not callable(persist_chain):
            raise EmbodiedConsequenceError("consequence_store_owner_invalid")
        persist_chain(expectation=expectation, handoff=handoff, renderer_report=renderer_report,
            observation=observation, attribution=attribution_base, comparison=comparison_base)
    return attribution_base, comparison_base


def world_state_records(*, expectation: EmbodiedActionExpectation, handoff: Mapping[str, Any],
                        renderer_report: AvatarRendererReport | None, observation: IndependentConsequenceObservation | None,
                        attribution: Mapping[str, Any], comparison: Mapping[str, Any]) -> list[dict[str, Any]]:
    verify_expectation(expectation)
    verify_renderer_handoff(handoff)
    if renderer_report is not None:
        verify_renderer_report(renderer_report)
    if observation is not None:
        verify_independent_observation(observation)
    _verify_consequence_attribution(attribution)
    semantic_comparison = {key: value for key, value in comparison.items()
        if key not in {"comparison_id", "comparison_digest"}}
    expected_comparison_id, expected_comparison_digest = _identity("prediction-comparison", semantic_comparison)
    if (comparison.get("schema_version") != COMPARISON_SCHEMA
            or comparison.get("comparison_id") != expected_comparison_id
            or comparison.get("comparison_digest") != expected_comparison_digest
            or dict(comparison.get("authority") or {}) != dict(FALSE_AUTHORITY)
            or comparison.get("expectation_id") != expectation.expectation_id
            or comparison.get("expectation_digest") != expectation.expectation_digest
            or comparison.get("observation_id") != (observation.observation_id if observation else None)
            or comparison.get("observation_digest") != (observation.observation_digest if observation else None)
            or attribution.get("expectation_id") != expectation.expectation_id
            or attribution.get("expectation_digest") != expectation.expectation_digest
            or attribution.get("handoff_id") != handoff.get("handoff_id")
            or attribution.get("handoff_digest") != handoff.get("handoff_digest")
            or attribution.get("comparison_id") != expected_comparison_id
            or attribution.get("comparison_digest") != expected_comparison_digest
            or attribution.get("observation_id") != (observation.observation_id if observation else None)
            or attribution.get("observation_digest") != (observation.observation_digest if observation else None)
            or expectation.handoff_id != handoff.get("handoff_id")
            or expectation.handoff_digest != handoff.get("handoff_digest")
            or expectation.correlation_id != handoff.get("correlation_id")
            or expectation.body_manifest_digest != handoff.get("body_manifest_digest")
            or (renderer_report is not None and (
                renderer_report.handoff_id != handoff.get("handoff_id")
                or renderer_report.handoff_digest != handoff.get("handoff_digest")
                or renderer_report.correlation_id != handoff.get("correlation_id")
                or renderer_report.artifact_digest != handoff.get("artifact_sha256")
                or renderer_report.manifest_digest != expectation.body_manifest_digest))
            or (observation is not None and (
                observation.expectation_id != expectation.expectation_id
                or observation.expectation_digest != expectation.expectation_digest
                or observation.handoff_id != handoff.get("handoff_id")
                or observation.handoff_digest != handoff.get("handoff_digest")
                or observation.correlation_id != handoff.get("correlation_id")
                or (renderer_report is not None and (
                    observation.renderer_report_id != renderer_report.report_id
                    or observation.renderer_report_digest != renderer_report.report_digest))))
            or attribution.get("renderer_report_id") != (renderer_report.report_id if renderer_report else None)
            or attribution.get("renderer_report_digest") != (renderer_report.report_digest if renderer_report else None)
            or attribution.get("effect_proven") is not False):
        raise EmbodiedConsequenceError("consequence_world_state_lineage_invalid")
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


def strategy_proposal_review_record(value: EmbodiedStrategyProposal, *,
        source_event_refs: Sequence[str] = (), experiment_result_id: str | None = None,
        experiment_result_digest: str | None = None, condition: str | None = None,
        execution_contexts: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Adapt a verified strategy proposal to the existing review-only owner.

    The digest remains explicit so a review cannot be reused for a substituted
    proposal. This projection is not a legacy feedback-action candidate and
    grants no admission, fulfillment, or execution authority.
    """
    verify_strategy_proposal(value)
    if (len(source_event_refs) > 16
            or any(not isinstance(item, str) or not item or len(item) > 256
                for item in source_event_refs)
            or len(execution_contexts) > 3
            or any(not isinstance(item, Mapping) or len(canonical_bytes(dict(item))) > 8192
                   for item in execution_contexts)):
        raise EmbodiedConsequenceError("strategy_review_source_reference_bounds_invalid")
    return {
        "proposal_id": value.strategy_id,
        "proposal_digest": value.strategy_digest,
        "proposal_kind": "embodied_strategy_proposal",
        "source_module": "sentientos.embodied_consequence",
        "blocked_effect_type": "strategy_proposal_review_only",
        "correlation_id": value.situation_binding,
        "source_event_refs": [f"strategy:{value.strategy_id}",
            f"strategy-digest:{value.strategy_digest}", *source_event_refs],
        "source_experiment_result_id": experiment_result_id,
        "source_experiment_result_digest": experiment_result_digest,
        "source_experiment_condition": condition,
        # These are context for a review, not claims that the proposed action
        # was authorized or performed. The source projection verifies each
        # governed receipt and keeps unknown execution rows explicit.
        "source_execution_contexts": [dict(item) for item in execution_contexts],
        "candidate_payload_summary": {
            "proposed_next_action_class": value.proposed_next_action_class,
            "requested_pose": value.requested_pose,
            "requested_expression": value.requested_expression,
            "more_observation_required": value.more_observation_required,
            "strategy_digest": value.strategy_digest,
        },
        "rationale": [value.rationale[:2000]],
        "risk_flags": {}, "privacy_retention_posture": "review",
        "review_status": "pending_review",
        "consent_posture": "not_asserted", "non_authoritative": True,
        "decision_power": "none", "approval_is_not_execution": True,
    }


class StrategyCognitionBackend(Protocol):
    def propose(self, *, condition: str, history: Sequence[Mapping[str, Any]], situation: Mapping[str, Any]) -> EmbodiedStrategyProposal: ...


STRATEGY_PROMPT_SCHEMA = {
    "schema_version": "sentientos.embodied_strategy_prompt:v2",
    "instruction": "Return only one JSON strategy proposal using the listed fields. Current World-State evidence is distinct from prior self-model and prior epistemic position; retained history is the only assigned condition difference. All three are non-authoritative context, not permission or policy. Propose only; do not claim execution, adoption, or observed consequences. Keep uncertainty explicit and do not infer physical effects from renderer output.",
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
        from .governed_local_model_invocation import GovernedLocalModelInvoker, LocalModelInvocationBudget
        from .resident_cognitive_model_serving import ResidentCognitiveModelServingInvoker, ResidentCognitiveServingSlot
        if not isinstance(caller, str) or not caller.strip() or len(caller) > 128:
            raise EmbodiedConsequenceError("governed_strategy_caller_invalid")
        if type(invoker) not in {GovernedLocalModelInvoker, ResidentCognitiveModelServingInvoker,
                ResidentCognitiveServingSlot}:
            raise EmbodiedConsequenceError("existing_governed_local_invoker_required")
        if resident_runtime_owner is not None:
            try:
                from .maintenance_resident_runtime_adoption import MaintenanceResidentRuntimeAdoptionController
            except ImportError as exc:
                raise EmbodiedConsequenceError("resident_software_generation_owner_unsupported_on_platform") from exc
            if type(resident_runtime_owner) is not MaintenanceResidentRuntimeAdoptionController:
                raise EmbodiedConsequenceError("resident_software_generation_owner_required")
        try:
            self.budget = LocalModelInvocationBudget(**dict(inference_budget))
        except (TypeError, ValueError) as exc:
            raise EmbodiedConsequenceError("governed_strategy_budget_invalid") from exc
        if (self.budget.max_input_chars < 1 or self.budget.max_output_chars < 1
                or self.budget.max_new_tokens < 1 or self.budget.timeout_seconds <= 0
                or self.budget.max_calls_per_correlation != 1
                or not isinstance(model_id, str) or not model_id
                or not isinstance(model_artifact_digest, str) or not model_artifact_digest):
            raise EmbodiedConsequenceError("governed_strategy_budget_or_model_binding_invalid")
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
            "history": [dict(item) for item in history], "situation": dict(situation),
            "cognitive_context": self.protocol.get("cognitive_context_projection")}
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
        history_event_time = self.protocol.get("history_record_created_at")
        inference_event_time = receipt_value.get("observed_at")
        if not isinstance(history_event_time, str) or not isinstance(inference_event_time, str):
            raise EmbodiedConsequenceError("strategy_event_time_unavailable")
        if _time(inference_event_time) <= _time(history_event_time):
            raise EmbodiedConsequenceError("strategy_inference_predates_history_record")
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
            "cognitive_context_digest": (digest(context["cognitive_context"])
                if context["cognitive_context"] is not None else None),
            "model_id": req["model_id"], "model_artifact_digest": req["model_artifact_digest"],
            "active_model_identity": dict(active_identity),
            "active_model_identity_digest": digest(dict(active_identity)),
            "authority_map_digest": req.get("authority_map_digest"),
            "serving_identity": dict(serving_identity) if isinstance(serving_identity, Mapping) else None,
            "serving_identity_posture": serving_identity_posture,
            "receipt_id": receipt_value.get("receipt_id"), "receipt_digest": receipt_value.get("receipt_digest"),
            "invocation_receipt": receipt_value,
            "response_digest": response_digest,
            "history_event_time": history_event_time,
            "inference_event_time": inference_event_time,
            "historical_event_precedes_inference": True,
            "proposal_id": proposal.strategy_id, "proposal_digest": proposal.strategy_digest,
            "software_generation_posture": software_posture,
            "software_execution_provenance_before": runtime_before,
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


def _strategy_proposal_from_mapping(value: Mapping[str, Any]) -> EmbodiedStrategyProposal:
    payload = dict(value)
    for name in ("relevant_consequence_ids", "factual_assertions"):
        if isinstance(payload.get(name), list): payload[name] = tuple(payload[name])
    try:
        proposal = EmbodiedStrategyProposal(**payload)
    except (TypeError, ValueError) as exc:
        raise EmbodiedConsequenceError("stored_strategy_proposal_invalid") from exc
    verify_strategy_proposal(proposal)
    return proposal


def _strategy_cognitive_context(value: Mapping[str, Any] | None, *,
                                protocol: Mapping[str, Any]) -> dict[str, Any] | None:
    if value is None:
        return None
    from .longitudinal_self_model import CognitiveSelfModelProjection
    from .persistent_epistemic_state import EpistemicCognitiveProjection
    from .resident_developmental_cognition import CurrentWorldStateCognitiveProjection
    from .world_state_board import WorldStateSnapshot, validate_snapshot
    expected_keys = {"current_tick", "tick_id", "snapshot", "current_projection",
        "prior_self_model", "prior_epistemic_state"}
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise EmbodiedConsequenceError("strategy_cognitive_context_shape_invalid")
    current_tick, tick_id = value.get("current_tick"), value.get("tick_id")
    snapshot, current = value.get("snapshot"), value.get("current_projection")
    self_model, epistemic = value.get("prior_self_model"), value.get("prior_epistemic_state")
    if (type(current_tick) is not int or current_tick < 0 or not isinstance(tick_id, str) or not tick_id
            or type(snapshot) is not WorldStateSnapshot
            or type(current) is not CurrentWorldStateCognitiveProjection
            or (self_model is not None and type(self_model) is not CognitiveSelfModelProjection)
            or (epistemic is not None and type(epistemic) is not EpistemicCognitiveProjection)):
        raise EmbodiedConsequenceError("strategy_cognitive_context_owner_types_invalid")
    snapshot_validation = validate_snapshot(snapshot)
    if (not snapshot_validation.valid or snapshot.validation_posture != "valid"
            or snapshot.digest != protocol.get("snapshot_digest")
            or current.snapshot_id != snapshot.snapshot_id
            or current.snapshot_digest != snapshot.digest
            or current.projection_digest != digest(current.semantic_payload())
            or current.projection_id != "current-world-state-" + current.projection_digest[7:31]
            or current.fact_ids != tuple(str(item.get("fact_id", "")) for item in current.facts)
            or len(current.fact_ids) > 16 or len(set(current.fact_ids)) != len(current.fact_ids)
            or not set(current.fact_ids) <= {fact.fact_id for fact in snapshot.facts}
            or current.read_only is not True or current.evidence_only is not True
            or current.current_truth is not False or current.authority is not False
            or current.policy is not False or current.goal is not False
            or current.canonical_explicit_user_retention is not False):
        raise EmbodiedConsequenceError("strategy_current_world_state_binding_invalid")
    current_payload: dict[str, Any] = {"tick_id": tick_id, "current_tick": current_tick,
        "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
        "current_world_state_projection": asdict(current)}
    if self_model is not None:
        self_digest = digest(self_model.semantic_payload())
        if (self_model.projection_digest != self_digest
                or self_model.projection_id != "cognitive-self-model-" + self_digest[7:31]
                or self_model.source_tick == tick_id
                or len(self_model.selected_claim_ids) != len(self_model.selected_claim_digests)
                or self_model.selected_claim_ids != tuple(str(claim.get("claim_id", "")) for claim in self_model.selected_claims)
                or self_model.selected_claim_digests != tuple(str(claim.get("semantic_digest", "")) for claim in self_model.selected_claims)
                or len(self_model.selected_claim_ids) > 64
                or any(self_model.authority.values()) or self_model.current_truth is not False
                or self_model.read_only is not True or self_model.derived_evidence is not True
                or self_model.interpretation is not False):
            raise EmbodiedConsequenceError("strategy_prior_self_model_binding_invalid")
        current_payload["prior_self_model"] = asdict(self_model)
    else:
        current_payload["prior_self_model"] = None
    if epistemic is not None:
        state_values = tuple(dict(item) for item in epistemic.states)
        state_bindings_valid = True
        for state in state_values:
            state_semantic = {key: item for key, item in state.items()
                if key not in {"state_id", "state_digest"}}
            state_digest = digest(state_semantic)
            if (state.get("state_digest") != state_digest
                    or state.get("state_id") != "epistemic-state:" + state_digest[7:31]
                    or not isinstance(state.get("authority"), Mapping)
                    or any(state["authority"].values())):
                state_bindings_valid = False
        if (epistemic.source_tick >= current_tick
                or len(state_values) > 64
                or not state_bindings_valid
                or tuple(str(item.get("proposition_id", "")) for item in state_values) != epistemic.proposition_ids
                or tuple(str(item.get("state_id", "")) for item in state_values) != epistemic.state_ids
                or tuple(str(item.get("state_digest", "")) for item in state_values) != epistemic.state_digests
                or tuple(int(item.get("generation", -1)) for item in state_values) != epistemic.generations
                or tuple(str(item.get("evidence_set_digest", "")) for item in state_values) != epistemic.evidence_set_digests
                or epistemic.evidence_only is not False or epistemic.prior_position_only is not True
                or epistemic.current_truth is not False or epistemic.authority is not False
                or epistemic.policy is not False or epistemic.goal is not False):
            raise EmbodiedConsequenceError("strategy_prior_epistemic_state_binding_invalid")
        semantic = {"source_tick": epistemic.source_tick,
            "proposition_ids": epistemic.proposition_ids, "state_ids": epistemic.state_ids,
            "state_digests": epistemic.state_digests, "generations": epistemic.generations,
            "evidence_set_digests": epistemic.evidence_set_digests, "states": epistemic.states,
            "evidence_only": False, "prior_position_only": True, "current_truth": False,
            "authority": False, "policy": False, "goal": False}
        projection_digest = digest(semantic)
        if (epistemic.projection_digest != projection_digest
                or epistemic.projection_id != "epistemic-projection:" + projection_digest[7:31]):
            raise EmbodiedConsequenceError("strategy_prior_epistemic_projection_digest_mismatch")
        current_payload["prior_epistemic_state"] = asdict(epistemic)
    else:
        current_payload["prior_epistemic_state"] = None
    if len(canonical_bytes(current_payload)) > MAX_STRATEGY_CONTEXT_BYTES:
        raise EmbodiedConsequenceError("strategy_cognitive_context_oversized")
    return current_payload


def _verify_strategy_execution_evidence(value: Mapping[str, Any], *, condition: str,
        protocol_id: str, protocol: Mapping[str, Any], history: Sequence[Mapping[str, Any]],
        history_record: Mapping[str, Any], situation: Mapping[str, Any],
        cognitive_context: Mapping[str, Any] | None,
        proposal: EmbodiedStrategyProposal) -> dict[str, Any]:
    from .governed_local_model_invocation import validate_receipt
    from .local_model_authority import digest_payload
    row = dict(value)
    row_digest = row.pop("association_digest", None)
    receipt = row.get("invocation_receipt")
    valid_receipt, _ = validate_receipt(receipt) if isinstance(receipt, Mapping) else (False, ["missing_receipt"])
    receipt_request = receipt.get("request") if isinstance(receipt, Mapping) else None
    request_semantic = ({key: item for key, item in receipt_request.items()
        if key not in {"request_id", "request_digest", "raw_prompt_stored", "ephemeral_prompt_handling"}}
        if isinstance(receipt_request, Mapping) else None)
    expected_request_digest = digest_payload(request_semantic) if request_semantic is not None else None
    situation_copy = json.loads(canonical_bytes(dict(situation)))
    expected_prompt = canonical_bytes({"schema": STRATEGY_PROMPT_SCHEMA,
        "condition": condition, "history": [dict(item) for item in history],
        "situation": situation_copy, "cognitive_context": cognitive_context}).decode("utf-8")
    linkage = receipt_request.get("linkage") if isinstance(receipt_request, Mapping) else None
    expected_correlation_id = _strategy_request_correlation_id(digest(dict(protocol)), condition)
    receipt_serving_identity = (linkage.get("resident_cognitive_serving")
        if isinstance(linkage, Mapping) else None)
    expected_serving_posture = ("verified_session_bound" if isinstance(receipt_serving_identity, Mapping)
        and all(receipt_serving_identity.get(key) for key in (
            "session_id", "model_serving_admission_ref", "activation_state_semantic_digest"))
        else "unknown_no_resident_serving_session")
    runtime_before = row.get("software_execution_provenance_before")
    runtime_after = row.get("software_execution_provenance")
    software_posture = row.get("software_generation_posture")
    provenance_rows = [item for item in (runtime_before, runtime_after) if item is not None]
    provenance_shapes_valid = all(isinstance(item, Mapping)
        and all(isinstance(item.get(key), str) and item.get(key) for key in (
            "provenance_digest", "process_instance_id", "represented_generation_digest"))
        for item in provenance_rows)
    software_identity_verified = (software_posture == "verified_current_resident_generation"
        and isinstance(runtime_before, Mapping) and isinstance(runtime_after, Mapping)
        and dict(runtime_before) == dict(runtime_after) and provenance_shapes_valid
        and runtime_after.get("represented_generation_digest") == protocol.get("software_generation"))
    legacy_software_provenance = (software_posture == "verified_current_resident_generation"
        and runtime_before is None and isinstance(runtime_after, Mapping) and provenance_shapes_valid
        and runtime_after.get("represented_generation_digest") == protocol.get("software_generation"))
    if (row_digest != digest(row) or not valid_receipt
            or row.get("condition") != condition
            or row.get("proposal_id") != proposal.strategy_id
            or row.get("proposal_digest") != proposal.strategy_digest
            or not isinstance(receipt_request, Mapping)
            or receipt.get("receipt_id") != row.get("receipt_id")
            or receipt.get("receipt_digest") != row.get("receipt_digest")
            or receipt_request.get("request_id") != row.get("request_id")
            or receipt_request.get("request_digest") != row.get("request_digest")
            or receipt_request.get("request_digest") != expected_request_digest
            or receipt_request.get("request_id") != "lmreq-" + str(expected_request_digest or "")[:24]
            or receipt_request.get("correlation_id") != expected_correlation_id
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
            or row.get("serving_identity") != (dict(receipt_serving_identity)
                if isinstance(receipt_serving_identity, Mapping) else None)
            or row.get("serving_identity_posture") != expected_serving_posture
            or not provenance_shapes_valid
            or (software_posture == "verified_current_resident_generation"
                and not (software_identity_verified or legacy_software_provenance))
            or not isinstance(linkage, Mapping)
            or linkage.get("experiment_condition") != condition
            or linkage.get("experiment_protocol_id") != protocol_id
            or linkage.get("history_record_ids") != [str(item.get("record_id", "")) for item in history]
            or row.get("history_digest") != digest([dict(item) for item in history])
            or row.get("situation_digest") != digest(dict(situation))
            or row.get("cognitive_context_digest") != (digest(cognitive_context)
                if cognitive_context is not None else None)
            or row.get("history_event_time") != history_record.get("created_at")
            or row.get("inference_event_time") != receipt.get("observed_at")
            or row.get("historical_event_precedes_inference") is not True
            or _time(str(receipt.get("observed_at"))) <= _time(str(history_record.get("created_at")))):
        raise EmbodiedConsequenceError("governed_execution_evidence_binding_invalid")
    row["association_digest"] = row_digest
    return row


def _strategy_request_correlation_id(protocol_digest: str, condition: str) -> str:
    """Stable call identity shared by the durable checkpoint and request."""
    return "strategy-experiment:" + digest({
        "protocol": protocol_digest, "condition": condition})[7:]


def run_strategy_experiment(*, protocol: Mapping[str, Any], history_record: Mapping[str, Any], situation: Mapping[str, Any],
                            backend: StrategyCognitionBackend, consequence: Mapping[str, Any],
                            store: "ConsequenceStore | None" = None,
                            cognitive_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    required={"protocol_id","snapshot_digest","body_generation","model_id","model_artifact_digest","inference_budget_digest",
              "prompt_schema_digest","renderer_situation_digest","software_generation","environment_fixture_digest"}
    if (set(protocol)!=required or len(canonical_bytes(dict(protocol)))>MAX_STRATEGY_CONTEXT_BYTES
            or any(not isinstance(protocol.get(key),str) or not protocol[key]
                   for key in required-{"body_generation"})
            or type(protocol.get("body_generation")) is not int or protocol["body_generation"]<1
            or len(canonical_bytes(dict(history_record)))>MAX_STRATEGY_CONTEXT_BYTES
            or len(canonical_bytes(dict(situation)))>MAX_STRATEGY_CONTEXT_BYTES):
        raise EmbodiedConsequenceError("strategy_protocol_shape_invalid")
    cognitive_context_projection = _strategy_cognitive_context(cognitive_context, protocol=protocol)
    _verify_consequence_attribution(consequence)
    consequence_context_binding = _strategy_prior_consequence_binding(history_record, consequence)
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
    if cognitive_context_projection is not None:
        candidate = history_record.get("candidate")
        history_binding_verified = (history_binding_verified and isinstance(candidate, Mapping)
            and candidate.get("snapshot_id") != cognitive_context_projection.get("snapshot_id"))
    history_event_time = history_record.get("created_at")
    try:
        if not isinstance(history_event_time, str): raise EmbodiedConsequenceError("history_event_time_missing")
        _time(history_event_time)
    except EmbodiedConsequenceError:
        history_binding_verified = False
    situation_digest=digest(dict(situation))
    situation_binding_verified=protocol.get("renderer_situation_digest")==situation_digest
    evidence_scope=_history_evidence_scope(history_record)
    conditions=("history_present","history_withheld","history_restored")
    protocol_id, protocol_digest = _identity("strategy-protocol", dict(protocol))
    bind_protocol = getattr(backend, "bind_protocol", None)
    if isinstance(backend, GovernedStrategyCognitionBackend) and store is None:
        raise EmbodiedConsequenceError("durable_store_required_for_governed_strategy_experiment")
    if callable(bind_protocol):
        bind_protocol({**dict(protocol), "protocol_id": protocol_id, "protocol_digest": protocol_digest,
            "history_record_created_at": history_event_time,
            "cognitive_context_projection": cognitive_context_projection})
    proposals=[]
    execution_evidence=[]
    condition_statuses=[]
    failure_posture=None
    execution_contradiction=False
    for condition in conditions:
        history=() if condition=="history_withheld" else (history_record,)
        request_correlation_id = _strategy_request_correlation_id(protocol_digest, condition)
        # Each call receives an independent canonical copy so a backend cannot
        # mutate shared context and contaminate a later control condition.
        situation_copy=json.loads(canonical_bytes(dict(situation)))
        condition_input_digest = digest({"protocol_id": protocol_id, "protocol_digest": protocol_digest,
            "condition": condition, "history": [dict(item) for item in history],
            "situation": situation_copy, "consequence_id": consequence.get("attribution_id"),
            "consequence_digest": consequence.get("attribution_digest"),
            "cognitive_context_digest": (digest(cognitive_context_projection)
                if cognitive_context_projection is not None else None),
            "target_history_record_id": history_record.get("record_id"),
            "target_history_record_digest": record_digest})
        if store is not None:
            start, terminal = store.read_strategy_condition(protocol_id=protocol_id,
                protocol_digest=protocol_digest, condition=condition, input_digest=condition_input_digest,
                request_correlation_id=request_correlation_id)
            if terminal is not None:
                condition_status = {"condition": condition, "status": terminal["status"],
                    "condition_result_digest": terminal["condition_result_digest"]}
                if terminal.get("status") == "completed" and isinstance(terminal.get("proposal"), Mapping):
                    condition_status["proposal_id"] = terminal["proposal"].get("strategy_id")
                    condition_status["proposal_digest"] = terminal["proposal"].get("strategy_digest")
                elif terminal.get("failure_posture") is not None:
                    condition_status["failure_posture"] = terminal["failure_posture"]
                condition_statuses.append(condition_status)
                if isinstance(terminal.get("execution_evidence"), Mapping):
                    stored_evidence = dict(terminal["execution_evidence"])
                else:
                    stored_evidence = None
                if terminal.get("status") != "completed":
                    if stored_evidence is not None:
                        execution_evidence.append(stored_evidence)
                    failure_posture = terminal.get("failure_posture") or "recovered_terminal_condition_incomplete"
                    execution_contradiction = terminal.get("status") == "contradictory"
                    break
                proposal_value = terminal.get("proposal")
                if not isinstance(proposal_value, Mapping):
                    execution_contradiction = True
                    failure_posture = "recovered_completed_condition_missing_proposal"
                    condition_statuses[-1]["status"] = "contradictory"
                    break
                proposal = _strategy_proposal_from_mapping(proposal_value)
                verify_strategy_proposal(proposal,
                    situation_binding=str(situation_copy.get("situation_binding", "")),
                    body_generation=int(protocol["body_generation"]))
                if stored_evidence is not None and stored_evidence.get("execution_posture") == "verified_governed_model_identity":
                    stored_evidence = _verify_strategy_execution_evidence(stored_evidence,
                        condition=condition, protocol_id=protocol_id, protocol=protocol,
                        history=history, history_record=history_record,
                        situation=situation_copy, cognitive_context=cognitive_context_projection,
                        proposal=proposal)
                    execution_evidence.append(stored_evidence)
                else:
                    execution_evidence.append(stored_evidence or {"condition":condition,
                        "execution_posture":"unknown_no_governed_receipt"})
                proposals.append(proposal)
                continue
            if start is not None:
                # An intent exists without a terminal record.  It may reflect a
                # live call or a crash after backend entry; either way it cannot
                # be retried safely.
                condition_statuses.append({"condition": condition, "status": "incomplete",
                    "failure_posture": "started_without_terminal_no_replay",
                    "request_correlation_id": start.get("request_correlation_id"),
                    "expected_request_correlation_id": request_correlation_id,
                    "request_correlation_binding_posture": "bound" if start.get("request_correlation_id")
                        == request_correlation_id else "legacy_missing"})
                failure_posture = "started_without_terminal_no_replay"
                break
            claimed, _ = store.begin_strategy_condition(protocol_id=protocol_id,
                protocol_digest=protocol_digest, condition=condition, input_digest=condition_input_digest,
                request_correlation_id=request_correlation_id)
            if not claimed:
                condition_statuses.append({"condition": condition, "status": "incomplete",
                    "failure_posture": "concurrent_or_recovered_condition_claim_no_replay",
                    "request_correlation_id": request_correlation_id})
                failure_posture = "concurrent_or_recovered_condition_claim_no_replay"
                break
        take_evidence = getattr(backend, "consume_execution_evidence", None)
        evidence = None
        proposal: EmbodiedStrategyProposal | None = None
        try:
            proposal = backend.propose(condition=condition,history=history,situation=situation_copy)
            evidence = take_evidence() if callable(take_evidence) else None
            if evidence is not None:
                if not isinstance(backend, GovernedStrategyCognitionBackend) or not isinstance(evidence, Mapping):
                    raise EmbodiedConsequenceError("unowned_governed_execution_evidence")
                row = _verify_strategy_execution_evidence(evidence, condition=condition,
                    protocol_id=protocol_id, protocol=protocol, history=history,
                    history_record=history_record, situation=situation_copy,
                    cognitive_context=cognitive_context_projection, proposal=proposal)
            else:
                row = {"condition": condition, "execution_posture": "unknown_no_governed_receipt"}
            verify_strategy_proposal(proposal, situation_binding=str(situation_copy.get("situation_binding", "")),
                body_generation=int(protocol["body_generation"]))
        except Exception as exc:
            if evidence is None and callable(take_evidence):
                evidence = take_evidence()
            condition_execution: dict[str, Any] | None = None
            if isinstance(evidence, Mapping):
                receipt = evidence.get("invocation_receipt")
                if isinstance(receipt, Mapping):
                    from .governed_local_model_invocation import validate_receipt
                    receipt_valid, _ = validate_receipt(receipt)
                    condition_execution = {"condition": condition,
                        "execution_posture": "incomplete_invocation_receipt",
                        "receipt_id": receipt.get("receipt_id"), "receipt_digest": receipt.get("receipt_digest"),
                        "receipt_valid": receipt_valid, "invocation_receipt": dict(receipt)}
                else:
                    condition_execution = {"condition": condition,
                        "execution_posture": "incomplete_or_contradictory_evidence",
                        "evidence_digest": digest(dict(evidence))}
            failure_posture = getattr(exc, "code", None) or "backend_failure:" + type(exc).__name__
            failure_text = str(failure_posture).lower()
            contradictory = any(marker in failure_text for marker in
                ("mismatch", "invalid", "contradictory", "malformed", "binding", "digest", "fields", "shape",
                 "not_json", "unowned"))
            execution_contradiction = execution_contradiction or contradictory
            if store is not None:
                terminal = store.finish_strategy_condition(protocol_id=protocol_id,
                    protocol_digest=protocol_digest, condition=condition, input_digest=condition_input_digest,
                    status="contradictory" if contradictory else "incomplete",
                    proposal=asdict(proposal) if isinstance(proposal, EmbodiedStrategyProposal) else None,
                    execution_evidence=condition_execution, failure_posture=str(failure_posture)[:128])
                condition_result_digest = terminal["condition_result_digest"]
            else:
                condition_result_digest = None
            if condition_execution is not None: execution_evidence.append(condition_execution)
            condition_statuses.append({"condition": condition, "status": "contradictory" if contradictory else "incomplete",
                "condition_result_digest":condition_result_digest,"failure_posture": str(failure_posture)[:128]})
            break
        if store is not None:
            terminal = store.finish_strategy_condition(protocol_id=protocol_id,
                protocol_digest=protocol_digest, condition=condition, input_digest=condition_input_digest,
                status="completed", proposal=asdict(proposal), execution_evidence=row)
        else:
            terminal = None
        proposals.append(proposal)
        execution_evidence.append(row)
        condition_statuses.append({"condition": condition, "status": "completed",
            "condition_result_digest": terminal.get("condition_result_digest") if terminal else None,
            "proposal_id": proposal.strategy_id, "proposal_digest": proposal.strategy_digest})
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
    if not experiment_complete:
        scoring = {"status":"not_scored_incomplete_execution", "authority":dict(FALSE_AUTHORITY)}
    elif consequence_context_binding.get("posture") != "verified_prior_selected_history":
        scoring = {"status":"not_scored_prior_consequence_not_bound_to_history",
            "consequence_context_posture": consequence_context_binding.get("posture"),
            "authority":dict(FALSE_AUTHORITY)}
    else:
        scoring = score_strategy_experiment(proposals=proposals, consequence=consequence)
    governed_rows = [item for item in execution_evidence if item.get("execution_posture") == "verified_governed_model_identity"]
    if experiment_contradictory:
        execution_posture = "contradictory_proposal_or_execution_evidence"
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
             and isinstance(item.get("software_execution_provenance_before"), Mapping)
             for item in governed_rows):
        if (len({digest(item.get("serving_identity")) for item in governed_rows}) == 1
                and len({digest(item.get("software_execution_provenance_before"))
                         for item in governed_rows}) == 1):
            execution_posture = "verified_governed_model_serving_and_running_software_generation"
        else:
            execution_posture = "contradictory_serving_identity_changed_across_conditions"
    else:
        execution_posture = "verified_model_identity_serving_or_software_identity_unknown_or_incomplete"
    current_projection = (cognitive_context_projection.get("current_world_state_projection")
        if cognitive_context_projection is not None else None)
    prior_self_model = (cognitive_context_projection.get("prior_self_model")
        if cognitive_context_projection is not None else None)
    prior_epistemic = (cognitive_context_projection.get("prior_epistemic_state")
        if cognitive_context_projection is not None else None)
    cognitive_context_complete = (isinstance(current_projection, Mapping)
        and isinstance(prior_self_model, Mapping) and isinstance(prior_epistemic, Mapping))
    execution_context_stable = (len(governed_rows) == len(conditions)
        and len({item.get("active_model_identity_digest") for item in governed_rows}) == 1
        and all(item.get("software_generation_posture") == "verified_current_resident_generation"
                and item.get("serving_identity_posture") == "verified_session_bound"
                and isinstance(item.get("software_execution_provenance_before"), Mapping)
                and isinstance(item.get("software_execution_provenance"), Mapping)
                for item in governed_rows)
        and len({digest(item.get("software_execution_provenance_before")) for item in governed_rows}) == 1
        and len({digest(item.get("software_execution_provenance")) for item in governed_rows}) == 1
        and len({item.get("authority_map_digest") for item in governed_rows}) == 1
        and len({digest(item.get("invocation_receipt", {}).get("generation_config"))
                 for item in governed_rows}) == 1
        and len({digest(item.get("serving_identity")) for item in governed_rows}) == 1
        and (cognitive_context_complete
            and len({item.get("cognitive_context_digest") for item in governed_rows}) == 1))
    temporal_separation_posture = ("historical_record_event_precedes_inference_logical_tick_unbound"
        if len(governed_rows) == len(conditions)
        and all(item.get("historical_event_precedes_inference") is True for item in governed_rows)
        else "unknown_or_incomplete")
    if experiment_contradictory:
        validity = "execution_or_proposal_identity_contradictory"
    elif not experiment_complete:
        validity = "execution_incomplete"
    elif not history_binding_verified or not situation_binding_verified:
        validity = "context_binding_incomplete"
    elif execution_posture == "verified_governed_model_serving_and_running_software_generation" and cognitive_context_complete:
        validity = "controlled_history_world_state_self_model_epistemic_and_execution_identity_consistent"
    elif execution_posture == "verified_governed_model_serving_and_running_software_generation":
        validity = "execution_identity_verified_cognitive_state_context_unbound"
    elif execution_posture.startswith("contradictory") or "contradictory" in execution_posture:
        validity = "execution_identity_contradictory"
    else:
        validity = "input_context_consistent_execution_identity_unknown_or_incomplete"
    cognitive_context_binding = {"posture": "verified_complete_prior_owner_projections"
            if cognitive_context_complete else "partial_or_unbound",
        "digest": digest(cognitive_context_projection) if cognitive_context_projection is not None else None,
        "tick_id": cognitive_context_projection.get("tick_id") if cognitive_context_projection is not None else None,
        "current_tick": cognitive_context_projection.get("current_tick") if cognitive_context_projection is not None else None,
        "snapshot_id": cognitive_context_projection.get("snapshot_id") if cognitive_context_projection is not None else None,
        "snapshot_digest": cognitive_context_projection.get("snapshot_digest") if cognitive_context_projection is not None else None,
        "current_projection_id": current_projection.get("projection_id") if isinstance(current_projection, Mapping) else None,
        "current_projection_digest": current_projection.get("projection_digest") if isinstance(current_projection, Mapping) else None,
        "current_fact_ids": current_projection.get("fact_ids", ()) if isinstance(current_projection, Mapping) else (),
        "self_model_projection_id": prior_self_model.get("projection_id") if isinstance(prior_self_model, Mapping) else None,
        "self_model_projection_digest": prior_self_model.get("projection_digest") if isinstance(prior_self_model, Mapping) else None,
        "self_model_source_tick": prior_self_model.get("source_tick") if isinstance(prior_self_model, Mapping) else None,
        "self_model_claim_ids": prior_self_model.get("selected_claim_ids", ()) if isinstance(prior_self_model, Mapping) else (),
        "self_model_claim_digests": prior_self_model.get("selected_claim_digests", ()) if isinstance(prior_self_model, Mapping) else (),
        "epistemic_projection_id": prior_epistemic.get("projection_id") if isinstance(prior_epistemic, Mapping) else None,
        "epistemic_projection_digest": prior_epistemic.get("projection_digest") if isinstance(prior_epistemic, Mapping) else None,
        "epistemic_source_tick": prior_epistemic.get("source_tick") if isinstance(prior_epistemic, Mapping) else None,
        "epistemic_state_ids": prior_epistemic.get("state_ids", ()) if isinstance(prior_epistemic, Mapping) else (),
        "epistemic_state_digests": prior_epistemic.get("state_digests", ()) if isinstance(prior_epistemic, Mapping) else (),
        "epistemic_evidence_set_digests": prior_epistemic.get("evidence_set_digests", ()) if isinstance(prior_epistemic, Mapping) else ()}
    payload={"schema_version":EXPERIMENT_RESULT_SCHEMA,"protocol":dict(protocol),"protocol_digest":digest(protocol),
        "condition_order":list(conditions),"withheld_record_id":history_record.get("record_id"),"withheld_record_digest":record_digest,
        "condition_statuses":condition_statuses,
        "experiment_completion_posture":"contradictory" if experiment_contradictory else "completed" if experiment_complete else "incomplete",
        "failure_posture":failure_posture,
        "history_record_identity_consistent":history_binding_verified,
        "situation_matches_declared_digest":situation_binding_verified,
        "world_state_binding_posture":"verified_resident_snapshot_and_current_projection"
            if cognitive_context_projection is not None else "protocol_snapshot_digest_declared_without_resident_snapshot_object",
        "self_model_binding_posture":"verified_prior_projection"
            if isinstance(prior_self_model, Mapping) else "unavailable_or_not_bound",
        "epistemic_state_binding_posture":"verified_prior_projection"
            if isinstance(prior_epistemic, Mapping) else "unavailable_or_not_bound",
        "cognitive_context_binding":cognitive_context_binding,
        "temporal_separation_posture":temporal_separation_posture,
        "cognitive_execution_identity_posture":execution_posture,
        "execution_context_stable_across_conditions":execution_context_stable if callable(bind_protocol) else None,
        "execution_evidence":execution_evidence,
        "consequence_scope":"prior_attribution_bound_to_selected_history_no_post_experiment_consequence_observed"
            if consequence_context_binding.get("posture") == "verified_prior_selected_history"
            else "prior_consequence_context_unbound_no_post_experiment_consequence_observed",
        "consequence_context_binding":consequence_context_binding,
        "input_context_digest":digest({"protocol_digest":protocol_digest,"situation":dict(situation),"history_record_id":history_record.get("record_id"),
            "history_record_digest":record_digest,"consequence_id":consequence.get("attribution_id"),
            "consequence_digest":consequence.get("attribution_digest")}),
        "evidence_scope":evidence_scope,
        "validity":validity,
        "proposals":[asdict(p) for p in proposals],"scoring":scoring,"no_retries":True,"improvement_claimed":False,"authority":dict(FALSE_AUTHORITY)}
    payload["experiment_result_id"],payload["experiment_result_digest"]=_identity("strategy-experiment",payload)
    if store is not None:
        store.put("strategy-experiments", payload["experiment_result_id"], payload)
    return payload


def _verify_consequence_attribution(value: Mapping[str, Any]) -> None:
    semantic=dict(value); claimed_id=semantic.pop("attribution_id",None); claimed_digest=semantic.pop("attribution_digest",None)
    expected_id,expected_digest=_identity("consequence",semantic)
    if claimed_id!=expected_id or claimed_digest!=expected_digest or dict(value.get("authority",{}))!=dict(FALSE_AUTHORITY):
        raise EmbodiedConsequenceError("consequence_attribution_binding_invalid")


def _strategy_prior_consequence_binding(history_record: Mapping[str, Any],
                                        consequence: Mapping[str, Any]) -> dict[str, Any]:
    candidate = history_record.get("candidate")
    facts = candidate.get("selected_facts") if isinstance(candidate, Mapping) else None
    if not isinstance(facts, (tuple, list)) or not facts:
        return {"posture":"selected_history_facts_unavailable",
            "attribution_id":consequence.get("attribution_id"),
            "attribution_digest":consequence.get("attribution_digest")}
    if len(facts) > 16:
        return {"posture":"selected_history_fact_limit_exceeded",
            "attribution_id":consequence.get("attribution_id"),
            "attribution_digest":consequence.get("attribution_digest")}
    attribution_id = consequence.get("attribution_id")
    attribution_digest = consequence.get("attribution_digest")
    exact_matches: list[Mapping[str, Any]] = []
    conflicting_source = False
    malformed_payload = False
    for fact in facts:
        if not isinstance(fact, Mapping):
            continue
        source = fact.get("source")
        payload = fact.get("payload")
        if not isinstance(source, Mapping) or source.get("source_id") != attribution_id:
            continue
        if (source.get("digest") != attribution_digest
                or source.get("schema_version") != consequence.get("schema_version")
                or source.get("kind") not in {"embodiment", "fulfillment"}):
            conflicting_source = True
            continue
        if not isinstance(payload, Mapping):
            malformed_payload = True
            continue
        try:
            _verify_consequence_attribution(payload)
        except EmbodiedConsequenceError:
            malformed_payload = True
            continue
        if (payload.get("attribution_id") != attribution_id
                or payload.get("attribution_digest") != attribution_digest
                or dict(payload) != dict(consequence)):
            malformed_payload = True
            continue
        exact_matches.append(fact)
    result = {"attribution_id":attribution_id,"attribution_digest":attribution_digest,
        "matched_fact_ids":[str(fact.get("fact_id", "")) for fact in exact_matches]}
    if conflicting_source:
        return {**result,"posture":"contradictory_history_source_digest"}
    if malformed_payload:
        return {**result,"posture":"history_consequence_payload_invalid"}
    if len(exact_matches) != 1:
        return {**result,"posture":"exact_history_consequence_missing_or_duplicated"}
    try:
        consequence_evaluated_at = _time(str(consequence.get("evaluated_at", "")))
        history_created_at = _time(str(history_record.get("created_at", "")))
    except EmbodiedConsequenceError:
        return {**result,"posture":"historical_evaluation_time_unavailable"}
    if consequence_evaluated_at >= history_created_at:
        return {**result,"posture":"consequence_does_not_precede_selected_history"}
    return {**result,"posture":"verified_prior_selected_history",
        "consequence_evaluated_at":consequence.get("evaluated_at"),
        "history_record_created_at":history_record.get("created_at"),
        "event_time_upper_bound":"consequence_evaluation_precedes_history_record"}


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


def validate_world_state_projection_config(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate explicit selection of immutable experiment evidence for World-State."""
    config = dict(value)
    base_fields = {"schema_version", "enabled", "store_root", "experiment_result_ids",
        "consequence_chain_ids",
        "model_replacement_state_root", "model_replacement_runs", "config_digest"}
    review_fields = {"proposal_review_log_path", "proposal_review_receipt_ids"}
    fulfillment_fields = {"fulfillment_receipt_log_path", "fulfillment_receipt_ids"}
    schema = config.get("schema_version")
    fields = base_fields | (review_fields if schema in {
        WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V2, WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V3} else set())
    if schema == WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V3:
        fields |= fulfillment_fields
    if (set(config) != fields or config.get("schema_version") != WORLD_STATE_PROJECTION_CONFIG_SCHEMA
            and config.get("schema_version") != WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V2
            and config.get("schema_version") != WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V3
            or type(config.get("enabled")) is not bool
            or config.get("config_digest") != digest({key: item for key, item in config.items()
                                                       if key != "config_digest"})):
        raise EmbodiedConsequenceError("world_state_projection_config_invalid")
    if not config["enabled"]:
        if (config["store_root"] is not None or config["experiment_result_ids"] != []
                or config["consequence_chain_ids"] != []
                or config["model_replacement_state_root"] is not None
                or config["model_replacement_runs"] != []
                or (config.get("proposal_review_log_path") is not None
                    or config.get("proposal_review_receipt_ids", []) != [])
                or (config.get("fulfillment_receipt_log_path") is not None
                    or config.get("fulfillment_receipt_ids", []) != [])):
            raise EmbodiedConsequenceError("disabled_world_state_projection_must_be_empty")
        return config
    root = config.get("store_root")
    identities = config.get("experiment_result_ids")
    chain_ids = config.get("consequence_chain_ids")
    replacement_root = config.get("model_replacement_state_root")
    replacement_runs = config.get("model_replacement_runs")
    review_path = config.get("proposal_review_log_path")
    review_ids = config.get("proposal_review_receipt_ids", [])
    fulfillment_path = config.get("fulfillment_receipt_log_path")
    fulfillment_ids = config.get("fulfillment_receipt_ids", [])
    if (not isinstance(identities, list) or len(identities) > 32
            or any(not isinstance(identity, str)
                   or not identity.startswith("strategy-experiment:")
                   or not _CONSEQUENCE_ID.fullmatch(identity) for identity in identities)
            or len(identities) != len(set(identities))
            or not isinstance(chain_ids, list) or len(chain_ids) > 32
            or any(not isinstance(identity, str)
                   or not identity.startswith("consequence-chain:")
                   or not _CONSEQUENCE_ID.fullmatch(identity) for identity in chain_ids)
            or len(chain_ids) != len(set(chain_ids))
            or (identities or chain_ids) and (not isinstance(root, str) or not Path(root).is_absolute())
            or not (identities or chain_ids) and root is not None
            or not isinstance(replacement_runs, list) or len(replacement_runs) > 32
            or not isinstance(review_ids, list) or len(review_ids) > 32
            or any(not isinstance(item, str) or len(item) != 29 or not item.startswith("eprr_")
                or any(character not in "0123456789abcdef" for character in item[5:]) for item in review_ids)
            or len(review_ids) != len(set(review_ids))
            or (review_ids and (not isinstance(review_path, str) or not Path(review_path).is_absolute()))
            or (not review_ids and review_path is not None)
            or not isinstance(fulfillment_ids, list) or len(fulfillment_ids) > 32
            or any(not isinstance(item, str) or len(item) != 28 or not item.startswith("efr_")
                or any(character not in "0123456789abcdef" for character in item[4:]) for item in fulfillment_ids)
            or len(fulfillment_ids) != len(set(fulfillment_ids))
            or (fulfillment_ids and (not isinstance(fulfillment_path, str)
                or not Path(fulfillment_path).is_absolute()))
            or (not fulfillment_ids and fulfillment_path is not None)):
        raise EmbodiedConsequenceError("world_state_projection_selection_invalid")
    if replacement_runs:
        prefix = "model-replacement-run-"
        if not isinstance(replacement_root, str) or not Path(replacement_root).is_absolute():
            raise EmbodiedConsequenceError("model_replacement_projection_root_invalid")
        seen: set[str] = set()
        for item in replacement_runs:
            if (not isinstance(item, Mapping) or set(item) != {"run_id", "run_digest"}
                    or not isinstance(item.get("run_id"), str)
                    or not item["run_id"].startswith(prefix)
                    or len(item["run_id"]) != len(prefix) + 24
                    or any(character not in "0123456789abcdef" for character in item["run_id"][len(prefix):])
                    or not isinstance(item.get("run_digest"), str)
                    or len(item["run_digest"]) != 71 or not item["run_digest"].startswith("sha256:")
                    or any(character not in "0123456789abcdef" for character in item["run_digest"][7:])
                    or item["run_id"] != prefix + item["run_digest"][7:31]
                    or item["run_id"] in seen):
                raise EmbodiedConsequenceError("model_replacement_projection_run_invalid")
            seen.add(item["run_id"])
    elif replacement_root is not None:
        raise EmbodiedConsequenceError("model_replacement_projection_root_without_runs")
    # A consequence chain produces at most seven records (expectation, handoff,
    # optional renderer report, optional independent observation, attribution,
    # comparison, and chain summary). Reserve an explicit aggregate budget so
    # the World-State builder cannot silently truncate selected evidence.
    projected_record_bound = (7 * len(chain_ids) + len(identities) + len(replacement_runs)
        + len(review_ids) + len(fulfillment_ids))
    if projected_record_bound > MAX_WORLD_STATE_PROJECTION_RECORDS:
        raise EmbodiedConsequenceError("world_state_projection_record_budget_exceeded")
    if not identities and not chain_ids and not replacement_runs and not review_ids and not fulfillment_ids:
        raise EmbodiedConsequenceError("world_state_projection_selection_empty")
    return config


class ConsequenceStore:
    """Immutable exact-chain store for consequence and experiment artifacts."""
    def __init__(self, root: Path, *, create_root: bool = True) -> None:
        if create_root or os.name != "nt":
            self._require_secure_platform()
        selected=Path(root)
        if os.name != "nt" and selected.is_symlink(): raise EmbodiedConsequenceError("consequence_store_root_symlink")
        if create_root:
            selected.mkdir(parents=True,exist_ok=True,mode=0o700)
        elif not selected.exists():
            raise EmbodiedConsequenceError("consequence_store_root_missing")
        if os.name != "nt" and (selected.is_symlink() or not selected.is_dir()): raise EmbodiedConsequenceError("consequence_store_root_invalid")
        self.root=selected.absolute() if os.name == "nt" else selected.resolve()
        self._read_only = not create_root

    @staticmethod
    def _require_secure_platform() -> None:
        required_dir_fd = (os.open, os.mkdir, os.stat, os.link, os.unlink)
        supported = (os.name == "posix" and _fcntl is not None
            and hasattr(os, "O_NOFOLLOW")
            and all(function in os.supports_dir_fd for function in required_dir_fd)
            and os.listdir in os.supports_fd)
        if not supported:
            raise EmbodiedConsequenceError(
                "consequence_store_unsupported_platform:secure_descriptor_relative_publication_unavailable")

    def _path(self, kind: str, identity: str, *, create_directory: bool = True) -> Path:
        if not (os.name == "nt" and self._read_only):
            self._require_secure_platform()
        if kind not in _CONSEQUENCE_KINDS or not isinstance(identity,str) or not _CONSEQUENCE_ID.fullmatch(identity):
            raise EmbodiedConsequenceError("consequence_artifact_selector_invalid")
        if os.name == "nt" and self._read_only:
            return self.root / kind / f"{identity}.json"
        directory_fd = self._open_kind_directory(kind, create=create_directory)
        os.close(directory_fd)
        return self.root/kind/f"{identity}.json"

    def _open_root_directory(self) -> int:
        """Walk the configured canonical root without following any path symlink."""
        ConsequenceStore._require_secure_platform()
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(os.sep, flags)
            for component in self.root.parts[1:]:
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
                metadata = os.fstat(next_descriptor)
                if not stat.S_ISDIR(metadata.st_mode):
                    os.close(next_descriptor)
                    raise EmbodiedConsequenceError("consequence_store_root_invalid")
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except EmbodiedConsequenceError:
            if "descriptor" in locals():
                os.close(descriptor)
            raise
        except OSError as exc:
            if "descriptor" in locals():
                os.close(descriptor)
            raise EmbodiedConsequenceError("consequence_store_root_invalid") from exc

    def _open_kind_directory(self, kind: str, *, create: bool) -> int:
        if kind not in _CONSEQUENCE_KINDS:
            raise EmbodiedConsequenceError("consequence_artifact_selector_invalid")
        root_fd = self._open_root_directory()
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            if create:
                try:
                    os.mkdir(kind, 0o700, dir_fd=root_fd)
                except FileExistsError:
                    pass
            try:
                directory_fd = os.open(kind, flags, dir_fd=root_fd)
            except FileNotFoundError as exc:
                raise EmbodiedConsequenceError("stored_artifact_missing") from exc
            metadata = os.fstat(directory_fd)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(directory_fd)
                raise EmbodiedConsequenceError("consequence_artifact_directory_invalid")
            return directory_fd
        except EmbodiedConsequenceError:
            raise
        except OSError as exc:
            raise EmbodiedConsequenceError("consequence_artifact_directory_invalid") from exc
        finally:
            os.close(root_fd)

    def _read(self, path: Path) -> bytes:
        if os.name == "nt" and self._read_only:
            kind = path.parent.name
            identity = path.name[:-5] if path.name.endswith(".json") else ""
            if (path.parent.parent != self.root or kind not in _CONSEQUENCE_KINDS
                    or not _CONSEQUENCE_ID.fullmatch(identity)):
                raise EmbodiedConsequenceError("consequence_artifact_selector_invalid")
            try:
                entries = read_regular_files(path.parent, max_entries=1,
                    max_file_bytes=MAX_CONSEQUENCE_ARTIFACT_BYTES,
                    max_total_bytes=MAX_CONSEQUENCE_ARTIFACT_BYTES,
                    selected_names=(path.name,))
            except WindowsHandleCustodyError as exc:
                raise EmbodiedConsequenceError("consequence_artifact_windows_read_failed") from exc
            if len(entries) != 1 or entries[0][0] != path.name:
                raise EmbodiedConsequenceError("stored_artifact_missing_or_ambiguous")
            return entries[0][1]
        self._require_secure_platform()
        kind = path.parent.name
        identity = path.name[:-5] if path.name.endswith(".json") else ""
        if (path.parent.parent != self.root or kind not in _CONSEQUENCE_KINDS
                or not _CONSEQUENCE_ID.fullmatch(identity)):
            raise EmbodiedConsequenceError("consequence_artifact_selector_invalid")
        directory_fd = self._open_kind_directory(kind, create=False)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            try:
                descriptor = os.open(path.name, flags, dir_fd=directory_fd)
            except FileNotFoundError as exc:
                raise EmbodiedConsequenceError("stored_artifact_missing") from exc
            except OSError as exc:
                raise EmbodiedConsequenceError("stored_artifact_missing_or_unsafe") from exc
        finally:
            os.close(directory_fd)
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

    def _publish_immutable(self, path: Path, data: bytes) -> bool:
        """Publish immutable evidence atomically without exceeding its kind cap."""
        if self._read_only:
            raise EmbodiedConsequenceError("consequence_store_read_only")
        self._require_secure_platform()
        if path.parent.parent != self.root or path.parent.name not in _CONSEQUENCE_KINDS:
            raise EmbodiedConsequenceError("consequence_artifact_selector_invalid")
        directory_fd = self._open_kind_directory(path.parent.name, create=False)
        lock_fd: int | None = None
        temporary_name: str | None = None
        try:
            try:
                lock_fd = os.open(".consequence-store.lock", os.O_CREAT | os.O_RDWR |
                    getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
                lock_metadata = os.fstat(lock_fd)
                lock_path_metadata = os.stat(".consequence-store.lock", dir_fd=directory_fd,
                    follow_symlinks=False)
                if (not stat.S_ISREG(lock_metadata.st_mode)
                        or (lock_metadata.st_dev, lock_metadata.st_ino)
                            != (lock_path_metadata.st_dev, lock_path_metadata.st_ino)):
                    raise EmbodiedConsequenceError("consequence_artifact_lock_invalid")
                assert _fcntl is not None
                _fcntl.flock(lock_fd, _fcntl.LOCK_EX)
            except OSError as exc:
                raise EmbodiedConsequenceError("consequence_artifact_lock_unavailable") from exc
            try:
                existing_fd = os.open(path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd)
            except FileNotFoundError:
                existing_fd = None
            except OSError as exc:
                raise EmbodiedConsequenceError("stored_artifact_missing_or_unsafe") from exc
            if existing_fd is not None:
                try:
                    metadata = os.fstat(existing_fd)
                    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CONSEQUENCE_ARTIFACT_BYTES:
                        raise EmbodiedConsequenceError("stored_artifact_unbounded_or_not_regular")
                    chunks: list[bytes] = []
                    remaining = MAX_CONSEQUENCE_ARTIFACT_BYTES + 1
                    while remaining:
                        chunk = os.read(existing_fd, min(65_536, remaining))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    existing = b"".join(chunks)
                    if len(existing) > MAX_CONSEQUENCE_ARTIFACT_BYTES:
                        raise EmbodiedConsequenceError("stored_artifact_unbounded_or_not_regular")
                    if existing != data:
                        raise EmbodiedConsequenceError("artifact_identity_collision")
                    return False
                finally:
                    os.close(existing_fd)
            artifact_count = sum(name.endswith(".json") for name in os.listdir(directory_fd))
            if artifact_count >= MAX_CONSEQUENCE_ARTIFACTS_PER_KIND:
                raise EmbodiedConsequenceError("consequence_artifact_retention_limit_exceeded")
            temporary_name = ".consequence-" + secrets.token_hex(16)
            temporary_fd = os.open(temporary_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
            with os.fdopen(temporary_fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary_name, path.name, src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd, follow_symlinks=False)
            except FileExistsError:
                existing = self._read(path)
                if existing != data:
                    raise EmbodiedConsequenceError("artifact_identity_collision")
                return False
            os.fsync(directory_fd)
            return True
        except OSError as exc:
            raise EmbodiedConsequenceError("consequence_artifact_publication_failed") from exc
        finally:
            if temporary_name is not None:
                try: os.unlink(temporary_name, dir_fd=directory_fd)
                except FileNotFoundError: pass
            if lock_fd is not None:
                try:
                    assert _fcntl is not None
                    _fcntl.flock(lock_fd, _fcntl.LOCK_UN)
                except OSError: pass
                os.close(lock_fd)
            os.close(directory_fd)

    def put(self, kind: str, identity: str, value: Mapping[str, Any]) -> Path:
        if self._read_only:
            raise EmbodiedConsequenceError("consequence_store_read_only")
        path=self._path(kind,identity)
        id_field,digest_field,prefix=_ARTIFACT_IDENTITIES[kind]
        semantic=dict(value); claimed_id=semantic.pop(id_field,None); claimed_digest=semantic.pop(digest_field,None)
        expected_id,expected_digest=_identity(prefix,semantic)
        if claimed_id!=identity or claimed_id!=expected_id or claimed_digest!=expected_digest:
            raise EmbodiedConsequenceError("artifact_identity_or_digest_invalid")
        data=canonical_bytes(value)+b"\n"
        if len(data)>MAX_CONSEQUENCE_ARTIFACT_BYTES: raise EmbodiedConsequenceError("artifact_size_bound_exceeded")
        self._publish_immutable(path, data)
        return path
    def get(self, kind: str, identity: str, *, digest_field: str) -> dict[str, Any]:
        path=self._path(kind,identity,create_directory=False)
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

    def put_consequence_chain(self, *, expectation: EmbodiedActionExpectation,
                              handoff: Mapping[str, Any], renderer_report: AvatarRendererReport | None,
                              observation: IndependentConsequenceObservation | None,
                              attribution: Mapping[str, Any], comparison: Mapping[str, Any]) -> dict[str, Any]:
        """Persist one validated consequence lineage bundle as a single immutable artifact."""
        projected = world_state_records(expectation=expectation, handoff=handoff,
            renderer_report=renderer_report, observation=observation,
            attribution=attribution, comparison=comparison)
        semantic: dict[str, Any] = {
            "schema_version": CONSEQUENCE_CHAIN_SCHEMA,
            "expectation": asdict(expectation), "handoff": dict(handoff),
            "renderer_report": asdict(renderer_report) if renderer_report is not None else None,
            "observation": asdict(observation) if observation is not None else None,
            "attribution": dict(attribution), "comparison": dict(comparison),
            "world_state_record_digests": [record["digest"] for record in projected],
            "effect_proven": False,
        }
        identity, chain_digest = _identity("consequence-chain", semantic)
        record = {**semantic, "chain_id": identity, "chain_digest": chain_digest}
        self.put("consequence-chains", identity, record)
        return record

    def load_verified_consequence_chain(self, chain_id: str) -> dict[str, Any]:
        record = self.get("consequence-chains", chain_id, digest_field="chain_digest")
        if (record.get("schema_version") != CONSEQUENCE_CHAIN_SCHEMA
                or record.get("effect_proven") is not False):
            raise EmbodiedConsequenceError("stored_consequence_chain_invalid")
        try:
            expectation_value = dict(record["expectation"])
            for name in ("observable_fields",):
                expectation_value[name] = tuple(expectation_value[name])
            expectation = EmbodiedActionExpectation(**expectation_value)
            report_value = record.get("renderer_report")
            report = None
            if report_value is not None:
                report_payload = dict(report_value)
                report_payload["warnings"] = tuple(report_payload["warnings"])
                report_payload["errors"] = tuple(report_payload["errors"])
                report = AvatarRendererReport(**report_payload)
            observation_value = record.get("observation")
            observation = (IndependentConsequenceObservation(**dict(observation_value))
                if observation_value is not None else None)
            projected = world_state_records(expectation=expectation,
                handoff=dict(record["handoff"]), renderer_report=report,
                observation=observation, attribution=dict(record["attribution"]),
                comparison=dict(record["comparison"]))
        except EmbodiedConsequenceError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbodiedConsequenceError("stored_consequence_chain_shape_invalid") from exc
        if [item["digest"] for item in projected] != record.get("world_state_record_digests"):
            raise EmbodiedConsequenceError("stored_consequence_chain_projection_conflict")
        return record

    def world_state_records(self, *, experiment_result_ids: Sequence[str] = (),
                            consequence_chain_ids: Sequence[str] = ()) -> list[dict[str, Any]]:
        """Project only explicitly selected, verified durable experiments as historical evidence.

        Selection is injected by an existing trusted owner; this method never
        discovers a directory or upgrades recovery time into event time.
        """
        from sentientos.world_state_board import record_digest

        identities = tuple(experiment_result_ids)
        chain_ids = tuple(consequence_chain_ids)
        if (len(identities) > 32 or len(chain_ids) > 32
                or any(not isinstance(identity, str) for identity in (*identities, *chain_ids))
                or len(identities) != len(set(identities))
                or len(chain_ids) != len(set(chain_ids))):
            raise EmbodiedConsequenceError("strategy_experiment_projection_selection_invalid")
        records: list[dict[str, Any]] = []
        for chain_id in chain_ids:
            chain = self.load_verified_consequence_chain(chain_id)
            expectation_value = dict(chain["expectation"])
            expectation_value["observable_fields"] = tuple(expectation_value["observable_fields"])
            expectation = EmbodiedActionExpectation(**expectation_value)
            report_value = chain.get("renderer_report")
            report = None
            if report_value is not None:
                report_payload = dict(report_value)
                report_payload["warnings"] = tuple(report_payload["warnings"])
                report_payload["errors"] = tuple(report_payload["errors"])
                report = AvatarRendererReport(**report_payload)
            observation_value = chain.get("observation")
            observation = (IndependentConsequenceObservation(**dict(observation_value))
                if observation_value is not None else None)
            chain_records = world_state_records(expectation=expectation,
                handoff=dict(chain["handoff"]), renderer_report=report,
                observation=observation, attribution=dict(chain["attribution"]),
                comparison=dict(chain["comparison"]))
            records.extend(chain_records)
            chain_record: dict[str, Any] = {
                "source_kind": "embodiment", "source_id": chain_id,
                "schema_version": CONSEQUENCE_CHAIN_SCHEMA, "subject_id": chain_id,
                "subject_kind": "embodied_consequence_chain", "stage": "observation",
                "disposition": "recorded", "evidence_strength": "digest_bound_consequence_chain",
                "payload": {"chain_id": chain_id, "chain_digest": chain["chain_digest"],
                    "component_source_ids": [item["source_id"] for item in chain_records],
                    "component_record_digests": [item["digest"] for item in chain_records],
                    "independent_observation_posture": ("unverified_caller_assertion"
                        if chain.get("observation") is not None else "no_observation"),
                    "current_truth": False, "effect_proven": False},
                "effect_claimed": False, "effect_proven": False,
            }
            chain_record["digest"] = record_digest(chain_record)
            records.append(chain_record)
        for identity in identities:
            result = self.get("strategy-experiments", identity,
                digest_field="experiment_result_digest")
            if result.get("schema_version") != EXPERIMENT_RESULT_SCHEMA:
                raise EmbodiedConsequenceError("stored_strategy_experiment_schema_invalid")
            protocol = result.get("protocol")
            if not isinstance(protocol, Mapping):
                raise EmbodiedConsequenceError("stored_strategy_experiment_protocol_invalid")
            if (result.get("protocol_digest") != digest(dict(protocol))
                    or result.get("authority") != dict(FALSE_AUTHORITY)
                    or result.get("improvement_claimed") is not False
                    or result.get("no_retries") is not True):
                raise EmbodiedConsequenceError("stored_strategy_experiment_binding_invalid")
            posture = result.get("experiment_completion_posture")
            if posture not in {"completed", "incomplete", "contradictory"}:
                raise EmbodiedConsequenceError("stored_strategy_experiment_posture_invalid")
            condition_order = result.get("condition_order")
            condition_statuses = result.get("condition_statuses")
            proposal_values = result.get("proposals")
            execution_rows = result.get("execution_evidence")
            if (condition_order != ["history_present", "history_withheld", "history_restored"]
                    or not isinstance(condition_statuses, list) or len(condition_statuses) > len(condition_order)
                    or not isinstance(proposal_values, list) or len(proposal_values) > len(condition_order)
                    or not isinstance(execution_rows, list) or len(execution_rows) > len(condition_order)):
                raise EmbodiedConsequenceError("stored_strategy_experiment_condition_lineage_invalid")
            statuses_by_proposal: dict[str, list[Mapping[str, Any]]] = {}
            for status in condition_statuses:
                if not isinstance(status, Mapping):
                    raise EmbodiedConsequenceError("stored_strategy_experiment_condition_lineage_invalid")
                proposal_id = status.get("proposal_id")
                if isinstance(proposal_id, str):
                    statuses_by_proposal.setdefault(proposal_id, []).append(status)
            execution_by_condition: dict[str, Mapping[str, Any]] = {}
            for execution in execution_rows:
                if not isinstance(execution, Mapping) or not isinstance(execution.get("condition"), str):
                    raise EmbodiedConsequenceError("stored_strategy_experiment_execution_lineage_invalid")
                if execution["condition"] in execution_by_condition:
                    raise EmbodiedConsequenceError("stored_strategy_experiment_execution_lineage_invalid")
                execution_by_condition[execution["condition"]] = execution
            proposal_record_digests: list[str] = []
            for proposal_value in proposal_values:
                if not isinstance(proposal_value, Mapping):
                    raise EmbodiedConsequenceError("stored_strategy_experiment_proposal_invalid")
                proposal = _strategy_proposal_from_mapping(proposal_value)
                proposal_statuses = statuses_by_proposal.get(proposal.strategy_id, [])
                matching_statuses = [status for status in proposal_statuses
                    if status.get("proposal_digest") == proposal.strategy_digest]
                if len(matching_statuses) != 1:
                    raise EmbodiedConsequenceError("stored_strategy_experiment_proposal_status_invalid")
                proposal_status = matching_statuses[0]
                condition = str(proposal_status.get("condition", ""))
                if (condition not in condition_order or proposal_status.get("status") not in {"completed", "contradictory"}):
                    raise EmbodiedConsequenceError("stored_strategy_experiment_proposal_status_invalid")
                execution = execution_by_condition.get(condition, {})
                execution_digest = digest(dict(execution)) if execution else None
                execution_posture = str(execution.get("execution_posture", "unknown_no_governed_receipt"))
                event_time = None
                receipt_id = receipt_digest = None
                resource_linkage = None
                invocation_request_context_linkage = None
                if execution:
                    association = dict(execution)
                    claimed_association = association.pop("association_digest", None)
                    receipt = execution.get("invocation_receipt")
                    receipt_valid = False
                    if isinstance(receipt, Mapping):
                        from .governed_local_model_invocation import validate_receipt
                        receipt_valid, _ = validate_receipt(receipt)
                    request = receipt.get("request") if isinstance(receipt, Mapping) else None
                    linkage = request.get("linkage") if isinstance(request, Mapping) else None
                    expected_experiment_protocol_id = _identity("strategy-protocol", dict(protocol))[0]
                    if (claimed_association != digest(association) or not receipt_valid
                            or not isinstance(receipt, Mapping)
                            or not isinstance(request, Mapping)
                            or execution.get("proposal_id") != proposal.strategy_id
                            or execution.get("proposal_digest") != proposal.strategy_digest
                            or receipt.get("receipt_id") != execution.get("receipt_id")
                            or receipt.get("receipt_digest") != execution.get("receipt_digest")
                            or request.get("request_id") != execution.get("request_id")
                            or request.get("request_digest") != execution.get("request_digest")
                            or request.get("purpose") != "resident_developmental_history_intervention_experiment"
                            or request.get("model_id") != protocol.get("model_id")
                            or request.get("model_artifact_digest") != protocol.get("model_artifact_digest")
                            or digest(request.get("budget")) != protocol.get("inference_budget_digest")
                            or request.get("active_model_identity") != execution.get("active_model_identity")
                            or execution.get("active_model_identity_digest") != digest(execution.get("active_model_identity"))
                            or receipt.get("status") != "admitted_completed"
                            or receipt.get("output_truncated") is not False
                            or receipt.get("fallback_occurred") is not False
                            or receipt.get("output_digest") != execution.get("response_digest")
                            or not isinstance(receipt.get("effects"), Mapping)
                            or receipt["effects"].get("local_model_inference") is not True
                            or request.get("correlation_id") != _strategy_request_correlation_id(
                                str(result.get("protocol_digest")), condition)
                            or not isinstance(linkage, Mapping)
                            or linkage.get("experiment_condition") != condition
                            or linkage.get("experiment_protocol_id") != expected_experiment_protocol_id
                            or execution_posture != "verified_governed_model_identity"):
                        execution_posture = "unverified_or_contradictory_execution_linkage"
                    else:
                        receipt_id = receipt.get("receipt_id")
                        receipt_digest = receipt.get("receipt_digest")
                        event_time = receipt.get("observed_at")
                        invocation_request_context_linkage = (dict(linkage)
                            if isinstance(linkage, Mapping) else None)
                        linked_allocation = receipt.get("resource_allocation_digest")
                        linked_attempt = receipt.get("resource_attempt_id")
                        linked_consumption = receipt.get("resource_consumption_receipt_digests")
                        linked_digest = receipt.get("resource_linkage_digest")
                        if (linked_allocation is not None or linked_attempt is not None
                                or bool(linked_consumption)):
                            # validate_receipt above authenticates this binding
                            # against the invocation receipt digest. This does
                            # not claim that the separate resource ledger was
                            # available here or independently reconciled.
                            resource_linkage = {
                                "posture": "invocation_receipt_bound_ledger_corroboration_not_performed",
                                "request_id": request.get("request_id"),
                                "request_digest": request.get("request_digest"),
                                "purpose": request.get("purpose"),
                                "model_id": request.get("model_id"),
                                "model_artifact_digest": request.get("model_artifact_digest"),
                                "allocation_digest": linked_allocation,
                                "attempt_id": linked_attempt,
                                "consumption_receipt_digests": list(linked_consumption or ()),
                                "linkage_digest": linked_digest,
                                "effect_receipt_id": receipt.get("receipt_id"),
                                "effect_receipt_digest": receipt_digest,
                            }
                        else:
                            resource_linkage = {
                                "posture": "legacy_or_unlinked_invocation",
                                "allocation_digest": None, "attempt_id": None,
                                "consumption_receipt_digests": [], "linkage_digest": None,
                                "effect_receipt_id": receipt.get("receipt_id"),
                                "effect_receipt_digest": receipt_digest,
                            }
                proposal_record: dict[str, Any] = {
                    "source_kind":"embodiment",
                    "source_id":f"strategy-experiment-proposal:{identity}:{proposal.strategy_id}",
                    "schema_version":STRATEGY_SCHEMA,
                    "subject_id":proposal.strategy_id,
                    "subject_kind":"embodied_strategy_proposal",
                    "stage":"proposal",
                    "disposition":"proposed",
                    "evidence_strength":"digest_bound_proposal_in_experiment_artifact",
                    "staleness":"unknown",
                    "payload":{
                        "experiment_result_id":identity,
                        "experiment_result_digest":result["experiment_result_digest"],
                        "experiment_protocol_id":_identity("strategy-protocol", dict(protocol))[0],
                        "declared_protocol_id":protocol.get("protocol_id"),
                        "experiment_protocol_digest":result.get("protocol_digest"),
                        "history_record_id":result.get("withheld_record_id"),
                        "history_record_digest":result.get("withheld_record_digest"),
                        "cognitive_context_binding":result.get("cognitive_context_binding"),
                        "condition":condition,
                        "condition_status":proposal_status.get("status"),
                        "strategy_id":proposal.strategy_id,
                        "strategy_digest":proposal.strategy_digest,
                        "proposed_next_action_class":proposal.proposed_next_action_class,
                        "requested_pose":proposal.requested_pose,
                        "requested_expression":proposal.requested_expression,
                        "rationale":proposal.rationale,
                        "uncertainty":proposal.uncertainty,
                        "relevant_consequence_ids":list(proposal.relevant_consequence_ids),
                        "factual_assertions":[dict(item) for item in proposal.factual_assertions],
                        "declared_model_id":protocol.get("model_id"),
                        "declared_model_artifact_digest":protocol.get("model_artifact_digest"),
                        "declared_software_generation":protocol.get("software_generation"),
                        "execution_posture":execution_posture,
                        "execution_evidence_digest":execution_digest,
                        "active_model_identity_digest":execution.get("active_model_identity_digest"),
                        "serving_identity_posture":execution.get("serving_identity_posture"),
                        "serving_identity_digest":digest(execution.get("serving_identity")) if execution.get("serving_identity") else None,
                        "software_generation_posture":execution.get("software_generation_posture"),
                        "software_execution_provenance_digest":digest(execution.get("software_execution_provenance")) if execution.get("software_execution_provenance") else None,
                        "invocation_receipt_id":receipt_id,
                        "invocation_receipt_digest":receipt_digest,
                        "resource_linkage":resource_linkage,
                        "invocation_request_context_linkage":invocation_request_context_linkage,
                        "event_time_posture":"invocation_receipt_time" if event_time else "undated",
                        "effect_proven":False,
                        "current_truth":False,
                        "authority":dict(FALSE_AUTHORITY),
                    },
                    "effect_claimed":False,
                    "effect_proven":False,
                }
                if event_time:
                    proposal_record["observed_at"] = str(event_time)
                proposal_record["digest"] = record_digest(proposal_record)
                if len(canonical_bytes(proposal_record)) > MAX_WORLD_STATE_PROJECTION_RECORD_BYTES:
                    raise EmbodiedConsequenceError("strategy_proposal_world_state_record_oversized")
                proposal_record_digests.append(proposal_record["digest"])
                records.append(proposal_record)
            record: dict[str, Any] = {
                "source_kind": "embodiment",
                "source_id": identity,
                "schema_version": EXPERIMENT_RESULT_SCHEMA,
                "subject_id": identity,
                "subject_kind": "embodied_strategy_experiment",
                "stage": "observation",
                "disposition": posture,
                "evidence_strength": "digest_bound_experiment_artifact",
                # The experiment artifact does not carry an authenticated event
                # timestamp. Keep the projection undated rather than assigning
                # reconstruction or current tick time.
                "payload": {
                    "experiment_result_id": identity,
                    "experiment_result_digest": result["experiment_result_digest"],
                    "protocol_id": protocol.get("protocol_id"),
                    "protocol_digest": result.get("protocol_digest"),
                    "history_record_id": result.get("withheld_record_id"),
                    "history_record_digest": result.get("withheld_record_digest"),
                    "validity": result.get("validity"),
                    "temporal_separation_posture": result.get("temporal_separation_posture"),
                    "cognitive_context_binding": result.get("cognitive_context_binding"),
                    "execution_posture": result.get("cognitive_execution_identity_posture"),
                    "evidence_scope": result.get("evidence_scope"),
                    "strategy_proposal_ids": [item.get("strategy_id") for item in proposal_values],
                    "strategy_proposal_digests": [item.get("strategy_digest") for item in proposal_values],
                    "strategy_proposal_record_digests": proposal_record_digests,
                    "effect_proven": False,
                    "current_truth": False,
                },
                "effect_claimed": False,
                "effect_proven": False,
            }
            record["digest"] = record_digest(record)
            if len(canonical_bytes(record)) > 32_768:
                raise EmbodiedConsequenceError("strategy_experiment_world_state_record_oversized")
            records.append(record)
        if len(records) > MAX_WORLD_STATE_PROJECTION_RECORDS:
            raise EmbodiedConsequenceError("world_state_projection_record_budget_exceeded")
        if any(len(canonical_bytes(record)) > MAX_WORLD_STATE_PROJECTION_RECORD_BYTES
               for record in records):
            raise EmbodiedConsequenceError("world_state_projection_record_oversized")
        return records

    def strategy_proposal_review_records(self, *, experiment_result_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Expose exact durable strategy proposals to the existing review-only owner."""
        identities = tuple(experiment_result_ids)
        if (len(identities) > 32 or any(not isinstance(item, str) for item in identities)
                or len(identities) != len(set(identities))):
            raise EmbodiedConsequenceError("strategy_review_selection_invalid")
        records: list[dict[str, Any]] = []
        for identity in identities:
            projection = self.world_state_records(experiment_result_ids=(identity,))
            projected_contexts: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for projected in projection:
                if projected.get("subject_kind") != "embodied_strategy_proposal":
                    continue
                payload = projected.get("payload")
                if not isinstance(payload, Mapping):
                    raise EmbodiedConsequenceError("stored_strategy_experiment_proposal_projection_invalid")
                context = {key: payload.get(key) for key in (
                    "condition", "history_record_id", "history_record_digest",
                    "invocation_receipt_id", "invocation_receipt_digest",
                    "execution_evidence_digest", "execution_posture",
                    "declared_model_id", "declared_model_artifact_digest",
                    "active_model_identity_digest", "serving_identity_posture",
                    "serving_identity_digest", "declared_software_generation",
                    "software_generation_posture", "software_execution_provenance_digest",
                    "resource_linkage", "invocation_request_context_linkage")}
                key = (str(projected.get("subject_id", "")), str(payload.get("strategy_digest", "")))
                if not all(key) or context["condition"] not in {
                        "history_present", "history_withheld", "history_restored"}:
                    raise EmbodiedConsequenceError("stored_strategy_experiment_proposal_projection_invalid")
                projected_contexts.setdefault(key, []).append(context)
            result = self.get("strategy-experiments", identity,
                digest_field="experiment_result_digest")
            protocol = result.get("protocol")
            if (result.get("schema_version") != EXPERIMENT_RESULT_SCHEMA
                    or not isinstance(protocol, Mapping)
                    or result.get("protocol_digest") != digest(dict(protocol))
                    or result.get("authority") != dict(FALSE_AUTHORITY)
                    or result.get("improvement_claimed") is not False
                    or result.get("no_retries") is not True
                    or result.get("experiment_completion_posture") not in {"completed", "incomplete", "contradictory"}):
                raise EmbodiedConsequenceError("stored_strategy_experiment_binding_invalid")
            statuses = result.get("condition_statuses")
            proposals = result.get("proposals")
            if not isinstance(statuses, list) or not isinstance(proposals, list):
                raise EmbodiedConsequenceError("stored_strategy_experiment_condition_lineage_invalid")
            for raw in proposals:
                if not isinstance(raw, Mapping):
                    raise EmbodiedConsequenceError("stored_strategy_experiment_proposal_invalid")
                proposal = _strategy_proposal_from_mapping(raw)
                matches = [item for item in statuses if isinstance(item, Mapping)
                    and item.get("proposal_id") == proposal.strategy_id
                    and item.get("proposal_digest") == proposal.strategy_digest]
                if len(matches) != 1 or matches[0].get("status") not in {"completed", "contradictory"}:
                    raise EmbodiedConsequenceError("stored_strategy_experiment_proposal_status_invalid")
                condition = matches[0].get("condition")
                if condition not in {"history_present", "history_withheld", "history_restored"}:
                    raise EmbodiedConsequenceError("stored_strategy_experiment_proposal_status_invalid")
                execution_contexts = projected_contexts.get((proposal.strategy_id, proposal.strategy_digest), [])
                if len(execution_contexts) != 1:
                    raise EmbodiedConsequenceError("stored_strategy_experiment_proposal_projection_ambiguous")
                records.append(strategy_proposal_review_record(proposal,
                    source_event_refs=(identity,
                        f"strategy-experiment-digest:{result['experiment_result_digest']}",
                        f"strategy-condition:{condition}"),
                    experiment_result_id=identity,
                    experiment_result_digest=result["experiment_result_digest"],
                    condition=str(condition), execution_contexts=execution_contexts))
        return records

    @staticmethod
    def _strategy_condition_id(protocol_id: str, condition: str) -> str:
        if condition not in ("history_present", "history_withheld", "history_restored"):
            raise EmbodiedConsequenceError("strategy_condition_invalid")
        return _identity("strategy-condition", {"protocol_id": protocol_id, "condition": condition})[0]

    def _checkpoint(self, kind: str, identity: str, *, digest_field: str,
                    expected_schema: str) -> dict[str, Any] | None:
        try:
            path = self._path(kind, identity, create_directory=False)
        except EmbodiedConsequenceError as exc:
            if str(exc) == "stored_artifact_missing":
                return None
            raise
        try:
            value = json.loads(self._read(path).decode("utf-8"))
        except EmbodiedConsequenceError as exc:
            if str(exc) == "stored_artifact_missing":
                return None
            raise
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise EmbodiedConsequenceError("strategy_condition_checkpoint_corrupt") from exc
        if not isinstance(value, dict) or value.get("schema_version") != expected_schema:
            raise EmbodiedConsequenceError("strategy_condition_checkpoint_corrupt")
        semantic = dict(value)
        claimed = semantic.pop(digest_field, None)
        if (claimed != digest(semantic) or value.get("condition_id") != identity
                or value.get("authority") != dict(FALSE_AUTHORITY)):
            raise EmbodiedConsequenceError("strategy_condition_checkpoint_digest_mismatch")
        return value

    def _create_checkpoint(self, kind: str, identity: str, value: Mapping[str, Any], *,
                           digest_field: str) -> bool:
        path = self._path(kind, identity)
        semantic = dict(value)
        if value.get(digest_field) != digest({key: item for key, item in semantic.items()
                                              if key != digest_field}):
            raise EmbodiedConsequenceError("strategy_condition_checkpoint_digest_invalid")
        data = canonical_bytes(value) + b"\n"
        if len(data) > MAX_CONSEQUENCE_ARTIFACT_BYTES:
            raise EmbodiedConsequenceError("strategy_condition_checkpoint_oversized")
        return self._publish_immutable(path, data)

    def begin_strategy_condition(self, *, protocol_id: str, protocol_digest: str,
                                 condition: str, input_digest: str,
                                 request_correlation_id: str) -> tuple[bool, dict[str, Any]]:
        if (not isinstance(request_correlation_id, str)
                or request_correlation_id != _strategy_request_correlation_id(protocol_digest, condition)):
            raise EmbodiedConsequenceError("strategy_condition_correlation_missing")
        condition_id = self._strategy_condition_id(protocol_id, condition)
        semantic = {"schema_version": STRATEGY_CONDITION_START_SCHEMA, "condition_id": condition_id,
            "protocol_id": protocol_id, "protocol_digest": protocol_digest,
            "condition": condition, "input_digest": input_digest,
            "request_correlation_id": request_correlation_id, "authority": dict(FALSE_AUTHORITY)}
        record = {**semantic, "condition_start_digest": digest(semantic)}
        created = self._create_checkpoint("strategy-experiment-starts", condition_id, record,
            digest_field="condition_start_digest")
        stored = self._checkpoint("strategy-experiment-starts", condition_id,
            digest_field="condition_start_digest", expected_schema=STRATEGY_CONDITION_START_SCHEMA)
        if stored != record:
            raise EmbodiedConsequenceError("strategy_condition_start_binding_conflict")
        return created, record

    def finish_strategy_condition(self, *, protocol_id: str, protocol_digest: str,
                                  condition: str, input_digest: str, status: str,
                                  proposal: Mapping[str, Any] | None,
                                  execution_evidence: Mapping[str, Any] | None,
                                  failure_posture: str | None = None) -> dict[str, Any]:
        if status not in {"completed", "incomplete", "contradictory"}:
            raise EmbodiedConsequenceError("strategy_condition_terminal_status_invalid")
        condition_id = self._strategy_condition_id(protocol_id, condition)
        start = self._checkpoint("strategy-experiment-starts", condition_id,
            digest_field="condition_start_digest", expected_schema=STRATEGY_CONDITION_START_SCHEMA)
        if (start is None or start.get("protocol_digest") != protocol_digest
                or start.get("input_digest") != input_digest or start.get("condition") != condition):
            raise EmbodiedConsequenceError("strategy_condition_start_missing_or_conflicting")
        if (start.get("request_correlation_id") is not None
                and start.get("request_correlation_id") != _strategy_request_correlation_id(protocol_digest, condition)):
            raise EmbodiedConsequenceError("strategy_condition_start_correlation_conflict")
        semantic = {"schema_version": STRATEGY_CONDITION_RESULT_SCHEMA, "condition_id": condition_id,
            "protocol_id": protocol_id, "protocol_digest": protocol_digest,
            "condition": condition, "input_digest": input_digest,
            "request_correlation_id": start.get("request_correlation_id"),
            "condition_start_digest": start["condition_start_digest"], "status": status,
            "proposal": dict(proposal) if proposal is not None else None,
            "execution_evidence": dict(execution_evidence) if execution_evidence is not None else None,
            "failure_posture": failure_posture, "authority": dict(FALSE_AUTHORITY)}
        record = {**semantic, "condition_result_digest": digest(semantic)}
        self._create_checkpoint("strategy-experiment-conditions", condition_id, record,
            digest_field="condition_result_digest")
        stored = self._checkpoint("strategy-experiment-conditions", condition_id,
            digest_field="condition_result_digest", expected_schema=STRATEGY_CONDITION_RESULT_SCHEMA)
        if stored != record:
            raise EmbodiedConsequenceError("strategy_condition_terminal_conflict")
        return record

    def read_strategy_condition(self, *, protocol_id: str, protocol_digest: str,
                                condition: str, input_digest: str,
                                request_correlation_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        condition_id = self._strategy_condition_id(protocol_id, condition)
        start = self._checkpoint("strategy-experiment-starts", condition_id,
            digest_field="condition_start_digest", expected_schema=STRATEGY_CONDITION_START_SCHEMA)
        terminal = self._checkpoint("strategy-experiment-conditions", condition_id,
            digest_field="condition_result_digest", expected_schema=STRATEGY_CONDITION_RESULT_SCHEMA)
        for value in (start, terminal):
            if value is not None and (value.get("protocol_id") != protocol_id
                    or value.get("protocol_digest") != protocol_digest
                    or value.get("condition") != condition
                    or value.get("input_digest") != input_digest
                    or (value.get("request_correlation_id") is not None
                        and value.get("request_correlation_id") != request_correlation_id)):
                raise EmbodiedConsequenceError("strategy_condition_recovery_context_conflict")
        if terminal is not None and (start is None or terminal.get("condition_start_digest") != start.get("condition_start_digest")
                or terminal.get("status") not in {"completed", "incomplete", "contradictory"}):
            raise EmbodiedConsequenceError("strategy_condition_recovery_lineage_invalid")
        return start, terminal
