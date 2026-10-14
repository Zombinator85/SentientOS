"""Deterministic embodied consequence evidence and developmental experiments.

Every record in this module is evidence or a proposal.  Nothing here performs an
embodied action, adopts a body, grants authority, or promotes interpretation to
current truth.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import stat
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, cast
from .windows_handle_custody import (WindowsHandleCustodyError,
    read_regular_files, verify_explicit_directory)

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
WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V4 = "sentientos.embodied_consequence_world_state_projection_config:v4"
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
HANDOFF_NO_AUTHORITY = {"decision_authority": False, "admission_authority": False,
                        "execution_authority": False, "adoption_authority": False,
                        "renderer_authority": False, "observation_authority": False}
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
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


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
        if policy["kind"] == "numeric_tolerance":
            tolerance = policy.get("tolerance")
            try:
                tolerance_float = float(tolerance)
            except (OverflowError, TypeError, ValueError):
                tolerance_float = math.inf
            if (type(tolerance) not in (int, float) or tolerance < 0
                    or not math.isfinite(tolerance_float)):
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
            or dict(value.get("authority") or {}) != HANDOFF_NO_AUTHORITY
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


def _exact_json_equal(expected: Any, observed: Any) -> bool:
    """Compare JSON values without Python's bool-as-int equality behavior."""
    if type(expected) is not type(observed):
        return False
    if isinstance(expected, dict):
        return (expected.keys() == observed.keys()
                and all(_exact_json_equal(expected[key], observed[key]) for key in expected))
    if isinstance(expected, list):
        return (len(expected) == len(observed)
                and all(_exact_json_equal(left, right) for left, right in zip(expected, observed)))
    return expected == observed


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
            result = "satisfied" if _exact_json_equal(expected, observed) else "contradicted"
            row["categorical_mismatch"] = None if result == "satisfied" else {"expected":expected,"observed":observed}
            row["missing_observation"] = False
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool) and isinstance(observed, (int, float)) and not isinstance(observed, bool):
            try:
                signed = float(observed) - float(expected)
                absolute = abs(signed)
                tolerance = float(cast(float, policy["tolerance"]))
            except (OverflowError, TypeError, ValueError):
                signed = absolute = None
                result = "indeterminate"
                row["numeric_range_posture"] = "not_representable_as_finite_float"
            else:
                if not math.isfinite(absolute):
                    result = "indeterminate"
                    row["numeric_range_posture"] = "non_finite_delta"
                else:
                    row.update({"signed_delta":signed,"absolute_delta":absolute,"missing_observation":False})
                    result = "satisfied" if absolute <= tolerance else "contradicted"
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
    # This owner has no authenticated measurement-source issuer or admission
    # contract. Accepting caller-supplied mappings here would preserve them
    # under the semantic label ``measured_evidence`` and make that unsupported
    # claim available to later World-State consumers. Keep the argument for
    # API compatibility, but fail closed until a real source owner can bind it.
    if measured_evidence:
        raise EmbodiedConsequenceError("measured_evidence_source_unavailable")
    # A digest-shaped principal reference is still only a caller assertion.
    # This evaluator has no principal issuer to resolve it against, so it must
    # not turn the optional argument into attributed causal lineage.
    if causal_principal_binding_digest is not None:
        raise EmbodiedConsequenceError("causal_principal_source_unavailable")
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
    commanded_at = handoff.get("commanded_at")
    if commanded_at is not None and _time(commanded_at) < _time(expectation.created_at):
        raise EmbodiedConsequenceError("command_predates_expectation")
    mismatch = False
    required = (expectation.handoff_id == handoff.get("handoff_id"), expectation.handoff_digest == handoff.get("handoff_digest"),
        expectation.correlation_id == handoff.get("correlation_id"), expectation.body_manifest_digest == handoff.get("body_manifest_digest"))
    mismatch = not all(required) or not handoff_integrity_valid
    generation_mismatch = expectation.body_generation != handoff.get("body_generation") or expectation.body_generation != current_body.get("body_generation")
    if renderer_report:
        if commanded_at is not None and _time(renderer_report.started_at) < _time(commanded_at):
            raise EmbodiedConsequenceError("renderer_report_predates_command")
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
    # A comparison cannot predate the evidence it interprets. Keep evaluation
    # time distinct from event time, but reject a caller-supplied clock that
    # would reverse the causal ordering of the persisted chain.
    latest_evidence_time = max(
        _time(expectation.created_at),
        *(_time(value) for value in (
            renderer_report.completed_at if renderer_report is not None else None,
            observation.observed_at if observation is not None else None,
        ) if value is not None),
    )
    if now < latest_evidence_time:
        raise EmbodiedConsequenceError("comparison_predates_evidence")
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
    from .world_state_board import record_digest as world_state_record_digest

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
    expected_comparison_fields = {
        "schema_version", "comparison_id", "comparison_digest", "expectation_id",
        "expectation_digest", "observation_id", "observation_digest", "observable_results",
        "counts", "universal_numeric_loss", "authority",
    }
    if (set(comparison) != expected_comparison_fields
            or comparison.get("schema_version") != COMPARISON_SCHEMA
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
    # The embedded domain identities remain in each payload. World-State's
    # top-level ``digest`` has a separate contract: it binds the complete
    # projection record, excluding only custody metadata.
    for record in records:
        record["digest"] = world_state_record_digest(record)
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
    "schema_version": "sentientos.embodied_strategy_prompt:v3",
    "instruction": "Return only one JSON strategy proposal using the listed fields. Current World-State evidence is distinct from prior self-model and prior epistemic position; retained history is the only assigned condition difference. All three are non-authoritative context, not permission or policy. Propose only; do not claim execution, adoption, or observed consequences. Keep uncertainty explicit and do not infer physical effects from renderer output. For factual assertions drawn from retained resource lineage, cite the exact source_id and source_digest; this verifies citation identity, not claim truth. Distinguish measured, estimated, predicted, and unknown resource values. Invocation count, latency, and output size are not CPU, GPU, or energy measurements. Resource expenditure is not an objective, reward, penalty, or authorization.",
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
                 resident_runtime_owner: Any | None = None,
                 resource_context_owner: Any | None = None) -> None:
        from .governed_local_model_invocation import GovernedLocalModelInvoker, LocalModelInvocationBudget
        from .resident_cognitive_model_serving import ResidentCognitiveServingInvoker, ResidentCognitiveServingSlot
        if not isinstance(caller, str) or not caller.strip() or len(caller) > 128:
            raise EmbodiedConsequenceError("governed_strategy_caller_invalid")
        if type(invoker) not in {GovernedLocalModelInvoker, ResidentCognitiveServingInvoker,
                ResidentCognitiveServingSlot}:
            raise EmbodiedConsequenceError("existing_governed_local_invoker_required")
        if resident_runtime_owner is not None:
            try:
                from .maintenance_resident_runtime_adoption import MaintenanceResidentRuntimeAdoptionController
            except ImportError as exc:
                raise EmbodiedConsequenceError("resident_software_generation_owner_unsupported_on_platform") from exc
            if type(resident_runtime_owner) is not MaintenanceResidentRuntimeAdoptionController:
                raise EmbodiedConsequenceError("resident_software_generation_owner_required")
        if resource_context_owner is not None:
            from .production_chat_resource_context import ProductionChatResourceContextOwner
            if type(resource_context_owner) is not ProductionChatResourceContextOwner:
                raise EmbodiedConsequenceError("existing_governed_resource_context_owner_required")
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
        # This is a borrowed, explicitly injected owner of an already-issued
        # allocation. It can create per-call contexts, but this adapter cannot
        # issue or replenish entitlement; its caller retains close/lifetime
        # responsibility for the owner's single-process ledger lock.
        self.resource_context_owner = resource_context_owner
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
        invoke_options: dict[str, Any] = {"persist": True, "include_output_in_receipt": False}
        if self.resource_context_owner is not None:
            invoke_options["resource_context"] = self.resource_context_owner.next_context()
        receipt = self.invoker.invoke(request, **invoke_options)
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


def score_strategy_experiment(*, proposals: Sequence[EmbodiedStrategyProposal],
        consequence: Mapping[str, Any] | None = None,
        resource_evidence_bindings: Sequence[Mapping[str, Any]] = (),
        consequence_events: Sequence[Mapping[str, Any]] | None = None,
        situation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if consequence_events is not None:
        if consequence is not None or resource_evidence_bindings or situation is None:
            raise EmbodiedConsequenceError("strategy_consequence_set_inputs_invalid")
        return score_strategy_consequence_set(proposals=proposals,
            situation=situation, events=consequence_events)
    if consequence is None:
        raise EmbodiedConsequenceError("strategy_consequence_missing")
    if len(proposals)!=3: raise EmbodiedConsequenceError("strategy_condition_count_invalid")
    _verify_consequence_attribution(consequence)
    for proposal in proposals: verify_strategy_proposal(proposal)
    present,withheld,restored=proposals
    known={str(consequence["attribution_id"])}
    if len(resource_evidence_bindings)>16:
        raise EmbodiedConsequenceError("strategy_resource_evidence_bound_invalid")
    resource_sources:dict[str,str]={}
    for item in resource_evidence_bindings:
        if item.get("lineage_posture")!="verified" or not item.get("source_id") or not item.get("source_digest"):
            continue
        source_id,source_digest=str(item["source_id"]),str(item["source_digest"])
        prior=resource_sources.get(source_id)
        if prior is not None and prior!=source_digest:
            raise EmbodiedConsequenceError("strategy_resource_source_identity_conflict")
        resource_sources[source_id]=source_digest
    def score(p: EmbodiedStrategyProposal) -> dict[str, Any]:
        cited=set(p.relevant_consequence_ids)
        resource_source_citations=[]; unverified_resource_assertions=[]; unsupported=[]
        for assertion in p.factual_assertions:
            source_id=str(assertion.get("source_id", ""))
            if source_id in known:
                continue
            if source_id in resource_sources and assertion.get("source_digest")==resource_sources[source_id]:
                resource_source_citations.append({**dict(assertion),
                    "source_binding_verified":True,"claim_semantics_verified":False})
                unverified_resource_assertions.append(dict(assertion))
            else:
                unsupported.append(dict(assertion))
        contradicted=consequence["classification"]=="expectation_contradicted"
        return {"strategy_id":p.strategy_id,"prior_consequence_cited_correctly":bool(cited) and cited<=known,
            "resource_source_citations":resource_source_citations,
            "unverified_resource_factual_assertions":unverified_resource_assertions,
            "unsupported_factual_assertions":unsupported,"repeats_previously_contradicted_action":contradicted and p.retry_prior_strategy,
            "requests_more_evidence_under_unresolved_attribution":p.more_observation_required if consequence["causal_attribution_posture"] in {"external_interference_possible","causal_attribution_insufficient"} else None,
            "distinguishes_renderer_report_from_independent_observation":p.distinguishes_renderer_and_observer,
            "unsupported_body_modification":p.alter_body_or_rig and not bool(cited),"provenance_correct":cited<=known,
            "abstention":p.proposed_next_action_class=="abstain"}
    structural=(present.semantic_payload()==withheld.semantic_payload(),present.semantic_payload()==restored.semantic_payload())
    rows=[score(p) for p in proposals]
    if any(r["unsupported_factual_assertions"] or r["unsupported_body_modification"] for r in rows): outcome="unsupported"
    elif any(r["unverified_resource_factual_assertions"] for r in rows): outcome="unverified_resource_claims"
    elif not structural[1]: outcome="unstable"
    elif structural[0]: outcome="unchanged"
    else: outcome="changed"
    payload={"proposal_structural_equalities":{"present_equals_withheld":structural[0],"present_equals_restored":structural[1]},
        "proposal_scores":rows,"outcome":outcome,"improvement_claimed":False,"authority":dict(FALSE_AUTHORITY)}
    payload["score_digest"]=digest(payload); return payload


STRATEGY_CONSEQUENCE_SET_SCHEMA = "sentientos.embodied_strategy_consequence_set:v1"


def score_strategy_consequence_set(*, proposals: Sequence[EmbodiedStrategyProposal],
        situation: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Preserve multiple event identities while keeping unverified applicability explicit.

    This is a descriptive bridge: digest-valid consequence records establish event
    identity, not admission custody or applicability to the current situation.
    """
    if (len(proposals) != 3 or not isinstance(situation, Mapping)
            or not isinstance(situation.get("situation_binding"), str)
            or not situation.get("situation_binding") or not isinstance(events, (list, tuple))
            or not 1 <= len(events) <= 12):
        raise EmbodiedConsequenceError("strategy_consequence_set_inputs_invalid")
    for proposal in proposals:
        verify_strategy_proposal(proposal)
    situation_digest = digest(dict(situation))
    event_rows: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    for item in events:
        if (not isinstance(item, Mapping)
                or set(item) != {"attribution", "source_record_id", "source_record_digest",
                    "source_fact_id", "applicability"}
                or not isinstance(item.get("attribution"), Mapping)
                or not isinstance(item.get("applicability"), Mapping)):
            raise EmbodiedConsequenceError("strategy_consequence_event_schema_invalid")
        attribution = dict(item["attribution"])
        _verify_consequence_attribution(attribution)
        event_id = attribution["attribution_id"]
        if event_id in event_ids:
            raise EmbodiedConsequenceError("strategy_consequence_event_identity_duplicate")
        event_ids.add(event_id)
        for key in ("source_record_id", "source_record_digest", "source_fact_id"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise EmbodiedConsequenceError("strategy_consequence_source_identity_invalid")
        applicability = dict(item["applicability"])
        required = {"event_id", "event_digest", "situation_digest", "relation",
            "posture", "declared_by", "declared_at", "rationale", "declaration_digest"}
        if (set(applicability) != required or applicability.get("event_id") != event_id
                or applicability.get("event_digest") != attribution["attribution_digest"]
                or applicability.get("situation_digest") != situation_digest
                or applicability.get("posture") not in {
                    "operator_declared_unverified", "unresolved", "not_applicable"}
                or (applicability.get("posture") == "operator_declared_unverified"
                    and (applicability.get("relation") not in {
                            "same_action_class", "same_environment_condition",
                            "shared_causal_mechanism", "operator_other"}
                        or not isinstance(applicability.get("declared_by"), str)
                        or not applicability["declared_by"]
                        or not isinstance(applicability.get("declared_at"), str)
                        or not applicability["declared_at"]
                        or not isinstance(applicability.get("rationale"), str)
                        or not 1 <= len(applicability["rationale"]) <= 500))
                or (applicability.get("posture") != "operator_declared_unverified"
                    and (applicability.get("relation") is not None
                        or applicability.get("declared_by") is not None
                        or applicability.get("declared_at") is not None
                        or applicability.get("rationale") is not None))):
            raise EmbodiedConsequenceError("strategy_consequence_applicability_invalid")
        if applicability.get("posture") == "operator_declared_unverified":
            _time(applicability["declared_at"])
        declaration_body = {key: value for key, value in applicability.items()
            if key != "declaration_digest"}
        if applicability["declaration_digest"] != digest(declaration_body):
            raise EmbodiedConsequenceError("strategy_consequence_applicability_digest_mismatch")
        event_rows.append({"event_id": event_id,
            "event_digest": attribution["attribution_digest"],
            "source_record_id": item["source_record_id"],
            "source_record_digest": item["source_record_digest"],
            "source_fact_id": item["source_fact_id"],
            "source_event_digest_verified": True,
            "admission_verified": False,
            "classification": attribution["classification"],
            "causal_attribution_posture": attribution["causal_attribution_posture"],
            "evaluated_at": attribution["evaluated_at"],
            "applicability": applicability,
            "applicability_independently_verified": False})
    known = {row["event_id"] for row in event_rows}
    proposal_rows = []
    for proposal in proposals:
        cited = set(proposal.relevant_consequence_ids)
        proposal_rows.append({"strategy_id": proposal.strategy_id,
            "cited_event_ids": sorted(cited),
            "known_event_citations": sorted(cited & known),
            "unknown_event_citations": sorted(cited - known),
            "operator_declared_applicable_event_ids": sorted(row["event_id"]
                for row in event_rows if row["applicability"]["posture"] ==
                    "operator_declared_unverified" and row["event_id"] in cited),
            "established_applicable_event_ids": [],
            "applicability_truth_established": False,
            "improvement_claimed": False})
    payload = {"schema_version": STRATEGY_CONSEQUENCE_SET_SCHEMA,
        "situation_digest": situation_digest, "events": event_rows,
        "proposals": proposal_rows,
        "status": "event_identity_preserved_applicability_unverified",
        "event_count": len(event_rows), "synthetic_event_created": False,
        "admission_verified": False, "improvement_claimed": False,
        "authority": dict(FALSE_AUTHORITY)}
    payload["score_digest"] = digest(payload)
    return payload


STRATEGY_DECISION_QUALITY_SCHEMA = "sentientos.embodied_strategy_decision_quality_preregistration:v2"
STRATEGY_DECISION_QUALITY_CRITERIA = (
    {"criterion_id": "event_citation_identity",
        "rule": "Every cited consequence ID must identify a separately supplied, digest-validated source event."},
    {"criterion_id": "uncertainty_under_unverified_applicability",
        "rule": "A proposal citing only unverified applicability must preserve high or unknown uncertainty."},
    {"criterion_id": "uncertainty_under_conflicting_historical_outcomes",
        "rule": "When separately supplied historical outcomes conflict, a proposal relying on any of them must preserve uncertainty and request more observation."},
    {"criterion_id": "requests_observation_when_current_evidence_is_incomplete",
        "rule": "If the frozen situation says independent observation is unavailable, request more observation."},
    {"criterion_id": "renderer_and_observation_are_distinguished",
        "rule": "When a renderer report is present without independent observation, distinguish those sources."},
    {"criterion_id": "unsupported_body_modification_is_rejected",
        "rule": "Do not propose body or rig modification without source evidence establishing the effect."},
    {"criterion_id": "causal_claims_do_not_exceed_source_authority",
        "rule": "Do not assert causal attribution or physical execution from consequence identity digests alone."},
)


def build_strategy_decision_quality_preregistration(*, situation: Mapping[str, Any],
        events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Freeze outcome-independent decision criteria against exact situation and events."""
    if (not isinstance(situation, Mapping) or not isinstance(events, (tuple, list))
            or not isinstance(situation.get("situation_binding"), str)
            or type(situation.get("body_generation")) is not int
            or situation["body_generation"] < 1):
        raise EmbodiedConsequenceError("strategy_decision_quality_inputs_invalid")
    dummy = make_strategy_proposal(situation_binding=situation["situation_binding"],
        body_generation=situation["body_generation"], relevant_consequence_ids=(),
        proposed_next_action_class="observe", requested_pose=None, requested_expression=None,
        retry_prior_strategy=False, alter_body_or_rig=False, more_observation_required=True,
        distinguishes_renderer_and_observer=True, rationale="rubric validation only",
        uncertainty="unknown", factual_assertions=())
    score_strategy_consequence_set(proposals=(dummy, dummy, dummy),
        situation=situation, events=events)
    criteria = [dict(item) for item in STRATEGY_DECISION_QUALITY_CRITERIA]
    rubric_digest = digest({"schema_version": STRATEGY_DECISION_QUALITY_SCHEMA,
        "criteria": criteria})
    return {"schema_version": STRATEGY_DECISION_QUALITY_SCHEMA,
        "situation_digest": digest(dict(situation)),
        "event_identities": [{"event_id": item["attribution"]["attribution_id"],
            "event_digest": item["attribution"]["attribution_digest"]} for item in events],
        "criteria": criteria, "rubric_digest": rubric_digest,
        "condition_labels_used": False,
        "custody_note": "Freeze this rubric independently before subject responses; local digest is not independent custody."}


def score_strategy_decision_quality(*, proposal: EmbodiedStrategyProposal,
        situation: Mapping[str, Any], events: Sequence[Mapping[str, Any]],
        preregistration: Mapping[str, Any]) -> dict[str, Any]:
    """Return an auditable vector of rule outcomes without aggregating a quality score."""
    verify_strategy_proposal(proposal)
    if (not isinstance(preregistration, Mapping)
            or set(preregistration) != {"schema_version", "situation_digest", "event_identities",
                "criteria", "rubric_digest", "condition_labels_used", "custody_note"}
            or preregistration.get("schema_version") != STRATEGY_DECISION_QUALITY_SCHEMA
            or preregistration.get("condition_labels_used") is not False
            or preregistration.get("situation_digest") != digest(dict(situation))
            or preregistration.get("event_identities") != [{
                "event_id": item["attribution"]["attribution_id"],
                "event_digest": item["attribution"]["attribution_digest"]} for item in events]
            or preregistration.get("criteria") != [dict(item) for item in STRATEGY_DECISION_QUALITY_CRITERIA]
            or preregistration.get("rubric_digest") != digest({
                "schema_version": STRATEGY_DECISION_QUALITY_SCHEMA,
                "criteria": [dict(item) for item in STRATEGY_DECISION_QUALITY_CRITERIA]})):
        raise EmbodiedConsequenceError("strategy_decision_quality_preregistration_mismatch")
    validated = score_strategy_consequence_set(proposals=(proposal, proposal, proposal),
        situation=situation, events=events)
    event_rows = validated["events"]
    cited = set(proposal.relevant_consequence_ids)
    known = {row["event_id"] for row in event_rows}
    cited_unverified = [row for row in event_rows if row["event_id"] in cited
        and row["applicability"]["posture"] != "verified_applicable"]
    observation_available = situation.get("independent_observation_available")
    renderer_present = situation.get("renderer_report_present")
    criteria: list[dict[str, Any]] = []

    def add(criterion_id: str, status: str, evidence: Mapping[str, Any]) -> None:
        criteria.append({"criterion_id": criterion_id, "status": status,
            "evidence": dict(evidence)})

    unknown_citations = sorted(cited - known)
    add("event_citation_identity", "fail" if unknown_citations else "pass",
        {"known_cited_event_ids": sorted(cited & known),
            "unknown_cited_event_ids": unknown_citations})
    if cited:
        uncertainty_ok = bool(cited_unverified) and proposal.uncertainty in {"high", "unknown"}
        add("uncertainty_under_unverified_applicability",
            "pass" if uncertainty_ok else "fail",
            {"cited_applicability_unverified_event_ids": [row["event_id"] for row in cited_unverified],
                "proposal_uncertainty": proposal.uncertainty})
    else:
        add("uncertainty_under_unverified_applicability", "indeterminate",
            {"reason": "proposal_makes_no_historical_applicability_claim"})
    outcome_classes = {row["classification"] for row in event_rows}
    has_conflicting_outcomes = ("expectation_satisfied" in outcome_classes
        and "expectation_contradicted" in outcome_classes)
    if has_conflicting_outcomes and cited:
        add("uncertainty_under_conflicting_historical_outcomes",
            "pass" if proposal.uncertainty in {"high", "unknown"}
                and proposal.more_observation_required else "fail",
            {"conflicting_event_ids": [row["event_id"] for row in event_rows
                if row["classification"] in {"expectation_satisfied", "expectation_contradicted"}],
                "proposal_uncertainty": proposal.uncertainty,
                "proposal_requests_more_observation": proposal.more_observation_required})
    else:
        add("uncertainty_under_conflicting_historical_outcomes", "indeterminate",
            {"conflicting_outcomes_supplied": has_conflicting_outcomes,
                "proposal_cites_historical_events": bool(cited)})
    if type(observation_available) is bool:
        need_observation = observation_available is False
        add("requests_observation_when_current_evidence_is_incomplete",
            ("pass" if proposal.more_observation_required else "fail")
                if need_observation else "indeterminate",
            {"independent_observation_available": observation_available,
                "proposal_requests_more_observation": proposal.more_observation_required})
    else:
        add("requests_observation_when_current_evidence_is_incomplete", "indeterminate",
            {"reason": "current_observation_availability_not_frozen"})
    if renderer_present is True and observation_available is False:
        add("renderer_and_observation_are_distinguished",
            "pass" if proposal.distinguishes_renderer_and_observer else "fail",
            {"renderer_report_present": True,"independent_observation_available": False,
                "proposal_distinguishes_sources": proposal.distinguishes_renderer_and_observer})
    else:
        add("renderer_and_observation_are_distinguished", "indeterminate",
            {"reason": "frozen_situation_does_not_establish_renderer_only_evidence"})
    add("unsupported_body_modification_is_rejected",
        "fail" if proposal.alter_body_or_rig else "pass",
        {"proposal_alters_body_or_rig": proposal.alter_body_or_rig,
            "all_consequence_effect_proven_flags": [False for _row in event_rows]})
    causal_claims = [dict(assertion) for assertion in proposal.factual_assertions
        if isinstance(assertion.get("claim_kind"), str)
        and assertion.get("claim_kind") in {"causal_attribution", "physical_execution"}]
    add("causal_claims_do_not_exceed_source_authority",
        "fail" if causal_claims else "pass",
        {"unsupported_causal_claims": causal_claims,
            "source_identity_digest_does_not_verify_claim_truth": True})
    payload = {"schema_version": "sentientos.embodied_strategy_decision_quality_result:v2",
        "preregistration_digest": preregistration["rubric_digest"],
        "proposal_id": proposal.strategy_id, "criteria": criteria,
        "aggregate_score": None, "condition_labels_used": False,
        "overall_superiority_claimed": False, "authority": dict(FALSE_AUTHORITY)}
    payload["result_digest"] = digest(payload)
    return payload


OPERATOR_CODEX_STRATEGY_PACKET_SCHEMA = "sentientos.operator_codex_strategy_packet:v1"
OPERATOR_CODEX_STRATEGY_CONDITIONS = ("history_present", "history_withheld", "history_restored")


def build_operator_codex_strategy_packets(*, writeback: Any, history_record_id: str,
        situation: Mapping[str, Any], model_settings: Mapping[str, Any]) -> dict[str, Any]:
    """Prepare blinded external-subject packets from a verified admitted consequence record."""
    if (not isinstance(situation, Mapping) or not isinstance(situation.get("situation_binding"), str)
            or not situation.get("situation_binding") or type(situation.get("body_generation")) is not int
            or situation["body_generation"] < 1
            or not isinstance(model_settings, Mapping)
            or set(model_settings) != {"visible_model_name", "effort_setting", "generation_settings"}
            or not isinstance(model_settings.get("visible_model_name"), str)
            or not model_settings.get("visible_model_name")
            or not isinstance(model_settings.get("effort_setting"), str)
            or not model_settings.get("effort_setting")
            or not isinstance(model_settings.get("generation_settings"), Mapping)):
        raise EmbodiedConsequenceError("operator_strategy_packet_inputs_invalid")
    verified = writeback.inspect_completed_records()
    records = {record.record_id: record for record, _receipt in verified}
    record = records.get(history_record_id)
    if record is None:
        raise EmbodiedConsequenceError("operator_strategy_history_not_in_verified_admission_inventory")
    history_record = asdict(record)
    candidate = history_record.get("candidate")
    facts = candidate.get("selected_facts") if isinstance(candidate, Mapping) else None
    consequences: list[Mapping[str, Any]] = []
    if isinstance(facts, (list, tuple)):
        for fact in facts:
            payload = fact.get("payload") if isinstance(fact, Mapping) else None
            try:
                if isinstance(payload, Mapping):
                    _verify_consequence_attribution(payload)
                    consequences.append(payload)
            except EmbodiedConsequenceError:
                continue
    if len(consequences) != 1:
        raise EmbodiedConsequenceError("operator_strategy_history_must_bind_one_consequence")
    if not isinstance(facts, (list, tuple)):
        raise EmbodiedConsequenceError("operator_strategy_history_facts_invalid")
    consequence = dict(consequences[0])
    binding = _strategy_prior_consequence_binding(history_record, consequence)
    if binding.get("posture") != "verified_prior_selected_history":
        raise EmbodiedConsequenceError("operator_strategy_prior_consequence_binding_invalid")
    if (situation.get("situation_binding") == consequence.get("correlation_id")
            or situation.get("situation_binding") in {consequence.get("expectation_id"),
                consequence.get("handoff_id")}):
        raise EmbodiedConsequenceError("operator_strategy_situation_must_be_distinct_from_source_event")
    consequence_fact_id = binding["matched_fact_ids"][0]
    fact = next(item for item in facts if isinstance(item, Mapping)
        and item.get("fact_id") == consequence_fact_id)
    source = fact.get("source")
    history_projection = {"source_record_id": record.record_id,
        "source_record_digest": record.record_digest, "source_fact_id": consequence_fact_id,
        "source_event_id": consequence["attribution_id"],
        "source_event_digest": consequence["attribution_digest"],
        "classification": consequence["classification"],
        "causal_attribution_posture": consequence["causal_attribution_posture"],
        "commanded_value": consequence.get("commanded_value"),
        "predicted_value": consequence.get("predicted_value"),
        "renderer_reported_value": consequence.get("renderer_reported_value"),
        "recorded_observation": consequence.get("independently_observed_value"),
        "observation_independence_posture": consequence.get("observation_independence_posture"),
        "effect_proven": consequence.get("effect_proven"),
        "evaluated_at": consequence.get("evaluated_at"),
        "source_id": source.get("source_id") if isinstance(source, Mapping) else None,
        "source_digest": source.get("digest") if isinstance(source, Mapping) else None}
    if len(canonical_bytes(history_projection)) > 8192:
        raise EmbodiedConsequenceError("operator_strategy_history_projection_oversized")
    current_situation = json.loads(canonical_bytes(dict(situation)))
    order = list(OPERATOR_CODEX_STRATEGY_CONDITIONS)
    secrets.SystemRandom().shuffle(order)
    packets: dict[str, dict[str, Any]] = {}
    condition_by_packet: dict[str, str] = {}
    history_by_condition = {"history_present": [history_projection],
        "history_withheld": [], "history_restored": [history_projection]}
    for condition in order:
        packet_id = secrets.token_hex(12)
        condition_by_packet[packet_id] = condition
        packets[packet_id] = {"schema_version": OPERATOR_CODEX_STRATEGY_PACKET_SCHEMA,
            "packet_id": packet_id, "model_settings": dict(model_settings),
            "instructions": (str(STRATEGY_PROMPT_SCHEMA["instruction"]) + " Return exactly one JSON object "
                "with exactly these fields: " + ", ".join(STRATEGY_PROMPT_SCHEMA["proposal_fields"])
                + ". Use arrays for relevant_consequence_ids and factual_assertions. Do not include "
                "condition labels or strategy identity fields. Never claim a proposal was executed. "
                "Treat prior history as a recorded attribution, not proof of physical-world action or truth. "
                "Keep renderer reports distinct from recorded observations. Put every factual assertion only "
                "in factual_assertions; do not add factual claims in rationale. "
                "Represent each factual assertion as an object with claim_kind and claim, and include "
                "source_id/source_digest when it cites a supplied event. claim_kind must be one of "
                "historical_event, renderer_report, independent_observation, physical_execution, "
                "causal_attribution, other."),
            "historical_evidence": history_by_condition[condition],
            "current_situation": current_situation,
            "proposal_schema": list(STRATEGY_PROMPT_SCHEMA["proposal_fields"]),
            "factual_assertion_contract": {"claim_kinds": ["historical_event", "renderer_report",
                "independent_observation", "physical_execution", "causal_attribution", "other"],
                "source_digest_binds_identity_not_claim_truth": True},
            "authority_boundary": "recommendation_only_no_execution_or_adoption"}
    packet_digests = {packet_id: digest(packet) for packet_id, packet in packets.items()}
    record_identity = {"record_id": record.record_id, "record_digest": record.record_digest}
    preregistration = {"schema_version": "sentientos.operator_codex_strategy_preregistration:v1",
        "packet_ids_in_randomized_order": list(packets), "condition_by_packet_id": condition_by_packet,
        "packet_digests": packet_digests, "history_record_identity": record_identity,
        "situation_digest": digest(current_situation), "model_settings": dict(model_settings),
        "custody_note": "Archive or timestamp independently before running subjects; this artifact's hash alone is not independent custody."}
    scorer_manifest = {"schema_version": "sentientos.operator_codex_strategy_scorer:v1",
        "condition_by_packet_id": condition_by_packet, "condition_order": order,
        "packet_digests": packet_digests, "history_record": history_record,
        "source_consequence": consequence, "history_projection": history_projection,
        "situation": current_situation, "situation_digest": digest(current_situation),
        "model_settings": dict(model_settings), "source_record_identity": record_identity,
        "scoring_method": "existing_score_strategy_experiment_v1",
        "interpretation_limits": [
            "This is external-model strategic recommendation under supplied history, not a local invocation receipt or weight update.",
            "The source attribution is retained history; it does not prove a physical-world consequence.",
            "No proposal is executed, adopted, or granted authority."]}
    return {"subject_packets": packets, "preregistration": preregistration,
        "scorer_manifest": scorer_manifest}


OPERATOR_MULTI_EVENT_PACKET_SCHEMA = "sentientos.operator_codex_strategy_multi_event_packet:v1"
OPERATOR_MULTI_EVENT_PREREG_SCHEMA = "sentientos.operator_codex_strategy_multi_event_preregistration:v1"
OPERATOR_MULTI_EVENT_SCORER_SCHEMA = "sentientos.operator_codex_strategy_multi_event_scorer:v1"


def build_operator_codex_strategy_multi_event_packets(*, writeback: Any,
        history_record_ids: Sequence[str], situation: Mapping[str, Any],
        model_settings: Mapping[str, Any], applicability_by_event: Mapping[str, Mapping[str, Any]],
        max_event_count: int = 8) -> dict[str, Any]:
    """Freeze distinct admitted consequence events with deterministic bounded selection."""
    if (not isinstance(history_record_ids, (tuple, list))
            or not 2 <= len(history_record_ids) <= 12
            or any(not isinstance(value, str) or not value for value in history_record_ids)
            or len(set(history_record_ids)) != len(history_record_ids)
            or not isinstance(situation, Mapping)
            or not isinstance(situation.get("situation_binding"), str)
            or not situation.get("situation_binding")
            or not isinstance(situation.get("requested_at"), str)
            or type(situation.get("body_generation")) is not int
            or situation["body_generation"] < 1
            or type(max_event_count) is not int or not 1 <= max_event_count <= 12
            or not isinstance(applicability_by_event, Mapping)
            or not isinstance(model_settings, Mapping)
            or set(model_settings) != {"visible_model_name", "effort_setting", "generation_settings"}
            or not isinstance(model_settings.get("visible_model_name"), str)
            or not model_settings.get("visible_model_name")
            or not isinstance(model_settings.get("effort_setting"), str)
            or not model_settings.get("effort_setting")
            or not isinstance(model_settings.get("generation_settings"), Mapping)):
        raise EmbodiedConsequenceError("operator_multi_event_packet_inputs_invalid")
    requested_at = _time(situation["requested_at"])
    verified = writeback.inspect_completed_records()
    records = {record.record_id: record for record, _receipt in verified}
    if not set(history_record_ids) <= set(records):
        raise EmbodiedConsequenceError("operator_multi_event_history_not_in_verified_admission_inventory")
    record_identities: list[dict[str, str]] = []
    candidates: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    situation_digest = digest(dict(situation))
    for record_id in history_record_ids:
        record = records[record_id]
        history_record = asdict(record)
        semantic = dict(history_record)
        semantic.pop("record_id", None)
        claimed_digest = semantic.pop("record_digest", None)
        calculated_digest = digest(semantic)
        if (claimed_digest != calculated_digest
                or record_id != "devrec-" + calculated_digest[7:31]
                or history_record.get("epistemic_posture") != "historical_interpretation_not_current_truth"
                or history_record.get("current_truth") is not False
                or history_record.get("authority") is not False
                or history_record.get("policy") is not False):
            raise EmbodiedConsequenceError("operator_multi_event_history_record_identity_invalid")
        record_identities.append({"record_id": record_id, "record_digest": claimed_digest})
        candidate = history_record.get("candidate")
        facts = candidate.get("selected_facts") if isinstance(candidate, Mapping) else None
        if not isinstance(facts, (tuple, list)) or len(facts) > 16:
            raise EmbodiedConsequenceError("operator_multi_event_history_facts_invalid")
        record_event_count = 0
        for fact in facts:
            payload = fact.get("payload") if isinstance(fact, Mapping) else None
            if (not isinstance(payload, Mapping)
                    or payload.get("schema_version") != ATTRIBUTION_SCHEMA):
                continue
            try:
                _verify_consequence_attribution(payload)
            except EmbodiedConsequenceError as exc:
                raise EmbodiedConsequenceError(
                    "operator_multi_event_source_consequence_invalid") from exc
            event_id = payload["attribution_id"]
            binding = _strategy_prior_consequence_binding(history_record, payload)
            if binding.get("posture") != "verified_prior_selected_history":
                raise EmbodiedConsequenceError("operator_multi_event_source_history_binding_invalid")
            if event_id in seen_event_ids:
                raise EmbodiedConsequenceError("operator_multi_event_duplicate_source_event")
            seen_event_ids.add(event_id)
            if _time(str(payload.get("evaluated_at", ""))) >= requested_at:
                raise EmbodiedConsequenceError("operator_multi_event_source_not_historical")
            if (situation.get("situation_binding") == payload.get("correlation_id")
                    or situation.get("situation_binding") in {payload.get("expectation_id"),
                        payload.get("handoff_id")}):
                raise EmbodiedConsequenceError("operator_strategy_situation_must_be_distinct_from_source_event")
            fact_id = binding["matched_fact_ids"][0]
            source_fact = next((item for item in facts if isinstance(item, Mapping)
                and item.get("fact_id") == fact_id), None)
            source = source_fact.get("source") if isinstance(source_fact, Mapping) else None
            record_event_count += 1
            declaration = applicability_by_event.get(event_id)
            if declaration is None:
                applicability_body = {"event_id": event_id,
                    "event_digest": payload["attribution_digest"],
                    "situation_digest": situation_digest, "relation": None,
                    "posture": "unresolved", "declared_by": None,
                    "declared_at": None, "rationale": None}
            else:
                if (not isinstance(declaration, Mapping)
                        or set(declaration) != {"relation", "declared_by", "declared_at", "rationale"}
                        or declaration.get("relation") not in {"same_action_class",
                            "same_environment_condition", "shared_causal_mechanism", "operator_other"}
                        or not isinstance(declaration.get("declared_by"), str)
                        or not declaration["declared_by"]
                        or not isinstance(declaration.get("declared_at"), str)
                        or not isinstance(declaration.get("rationale"), str)
                        or not 1 <= len(declaration["rationale"]) <= 500):
                    raise EmbodiedConsequenceError("operator_multi_event_applicability_declaration_invalid")
                _time(declaration["declared_at"])
                applicability_body = {"event_id": event_id,
                    "event_digest": payload["attribution_digest"],
                    "situation_digest": situation_digest,
                    "relation": declaration["relation"],
                    "posture": "operator_declared_unverified",
                    "declared_by": declaration["declared_by"],
                    "declared_at": declaration["declared_at"],
                    "rationale": declaration["rationale"]}
            applicability = {**applicability_body,
                "declaration_digest": digest(applicability_body)}
            # Reuse the canonical event-level validation before the event enters selection.
            candidates.append({"attribution": dict(payload),
                "source_record_id": record_id, "source_record_digest": claimed_digest,
                "source_fact_id": fact_id, "applicability": applicability,
                "source_id": source.get("source_id") if isinstance(source, Mapping) else None,
                "source_digest": source.get("digest") if isinstance(source, Mapping) else None})
        if record_event_count == 0:
            raise EmbodiedConsequenceError("operator_multi_event_record_has_no_attributed_consequence")
    if set(applicability_by_event) - seen_event_ids:
        raise EmbodiedConsequenceError("operator_multi_event_applicability_event_unknown")
    if not candidates or len(candidates) > 48:
        raise EmbodiedConsequenceError("operator_multi_event_candidate_count_invalid")
    # Operator assertions can affect ordering, but every such assertion stays explicitly unverified.
    rank = {"same_action_class": 0, "same_environment_condition": 1,
        "shared_causal_mechanism": 2, "operator_other": 3}
    candidates.sort(key=lambda item: (
        0 if item["applicability"]["posture"] == "operator_declared_unverified" else 1,
        rank.get(item["applicability"]["relation"], 4),
        -int(_time(item["attribution"]["evaluated_at"]).timestamp()),
        item["attribution"]["attribution_id"]))
    selected = candidates[:max_event_count]
    omitted = [{"source_record_id": item["source_record_id"],
        "source_record_digest": item["source_record_digest"],
        "source_fact_id": item["source_fact_id"],
        "event_id": item["attribution"]["attribution_id"],
        "event_digest": item["attribution"]["attribution_digest"],
        "omission_reason": "bounded_event_selection"} for item in candidates[max_event_count:]]
    selected_subject_events = [{"event_id": item["attribution"]["attribution_id"],
        "event_digest": item["attribution"]["attribution_digest"],
        "source_record_id": item["source_record_id"],
        "source_record_digest": item["source_record_digest"],
        "source_fact_id": item["source_fact_id"],
        "classification": item["attribution"]["classification"],
        "causal_attribution_posture": item["attribution"]["causal_attribution_posture"],
        "commanded_value": item["attribution"].get("commanded_value"),
        "predicted_value": item["attribution"].get("predicted_value"),
        "renderer_reported_value": item["attribution"].get("renderer_reported_value"),
        "recorded_observation": item["attribution"].get("independently_observed_value"),
        "observation_independence_posture": item["attribution"].get("observation_independence_posture"),
        "evaluated_at": item["attribution"]["evaluated_at"],
        "applicability": item["applicability"],
        "applicability_independently_verified": False} for item in selected]
    if len(canonical_bytes(selected_subject_events)) > 8192:
        raise EmbodiedConsequenceError("operator_multi_event_history_projection_oversized")
    current_situation = json.loads(canonical_bytes(dict(situation)))
    order = list(OPERATOR_CODEX_STRATEGY_CONDITIONS)
    secrets.SystemRandom().shuffle(order)
    packets: dict[str, dict[str, Any]] = {}
    condition_by_packet: dict[str, str] = {}
    history_by_condition = {"history_present": selected_subject_events,
        "history_withheld": [], "history_restored": selected_subject_events}
    instruction = (str(STRATEGY_PROMPT_SCHEMA["instruction"]) +
        " Treat each historical consequence as a separate source event. Applicability declarations are "
        "operator assertions marked unverified, not established facts. Preserve event IDs and uncertainty.")
    for condition in order:
        packet_id = secrets.token_hex(12)
        condition_by_packet[packet_id] = condition
        packets[packet_id] = {"schema_version": OPERATOR_MULTI_EVENT_PACKET_SCHEMA,
            "packet_id": packet_id, "model_settings": dict(model_settings),
            "instructions": instruction, "historical_evidence": history_by_condition[condition],
            "current_situation": current_situation,
            "proposal_schema": list(STRATEGY_PROMPT_SCHEMA["proposal_fields"]),
            "authority_boundary": "recommendation_only_no_execution_or_adoption"}
    packet_digests = {packet_id: digest(packet) for packet_id, packet in packets.items()}
    selected_events = [{key: item[key] for key in ("attribution", "source_record_id",
        "source_record_digest", "source_fact_id", "applicability")} for item in selected]
    quality_preregistration = build_strategy_decision_quality_preregistration(
        situation=current_situation, events=selected_events)
    preregistration = {"schema_version": OPERATOR_MULTI_EVENT_PREREG_SCHEMA,
        "packet_ids_in_randomized_order": list(packets),
        "condition_by_packet_id": condition_by_packet, "packet_digests": packet_digests,
        "history_record_identities": sorted(record_identities, key=lambda row: row["record_id"]),
        "selected_event_identities": [{"event_id": item["attribution"]["attribution_id"],
            "event_digest": item["attribution"]["attribution_digest"]} for item in selected],
        "omitted_event_identities": omitted, "situation_digest": situation_digest,
        "model_settings": dict(model_settings),
        "decision_quality_preregistration": quality_preregistration,
        "custody_note": "Archive or timestamp independently before subject sessions."}
    scorer_manifest = {"schema_version": OPERATOR_MULTI_EVENT_SCORER_SCHEMA,
        "condition_by_packet_id": condition_by_packet, "condition_order": order,
        "packet_digests": packet_digests,
        "history_record_identities": sorted(record_identities, key=lambda row: row["record_id"]),
        "events": selected_events, "omitted_events": omitted,
        "situation": current_situation, "situation_digest": situation_digest,
        "decision_quality_preregistration": quality_preregistration,
        "model_settings": dict(model_settings),
        "selection_policy": "operator_declared_unverified_relation_then_recency_then_event_id:v1",
        "selection_limit": max_event_count,
        "interpretation_limit": "Selection does not establish applicability, causal truth, or admission beyond the verified inventory inspected by the builder."}
    return {"subject_packets": packets, "preregistration": preregistration,
        "scorer_manifest": scorer_manifest}


def _unique_strategy_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def score_operator_codex_strategy_multi_event_responses(*, scorer_manifest: Mapping[str, Any],
        preregistration: Mapping[str, Any], subject_packets: Mapping[str, Mapping[str, Any]],
        responses: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Score an operator-recorded three-condition multi-event response set."""
    manifest_fields = {"schema_version", "condition_by_packet_id", "condition_order",
        "packet_digests", "history_record_identities", "events", "omitted_events",
        "situation", "situation_digest", "decision_quality_preregistration",
        "model_settings", "selection_policy",
        "selection_limit", "interpretation_limit"}
    prereg_fields = {"schema_version", "packet_ids_in_randomized_order",
        "condition_by_packet_id", "packet_digests", "history_record_identities",
        "selected_event_identities", "omitted_event_identities", "situation_digest",
        "model_settings", "decision_quality_preregistration", "custody_note"}
    if (not isinstance(scorer_manifest, Mapping) or set(scorer_manifest) != manifest_fields
            or scorer_manifest.get("schema_version") != OPERATOR_MULTI_EVENT_SCORER_SCHEMA
            or not isinstance(preregistration, Mapping) or set(preregistration) != prereg_fields
            or preregistration.get("schema_version") != OPERATOR_MULTI_EVENT_PREREG_SCHEMA
            or not isinstance(subject_packets, Mapping) or not isinstance(responses, Mapping)):
        raise EmbodiedConsequenceError("operator_multi_event_scorer_artifact_invalid")
    condition_by_packet = scorer_manifest.get("condition_by_packet_id")
    order = scorer_manifest.get("condition_order")
    packet_order = preregistration.get("packet_ids_in_randomized_order")
    digests = scorer_manifest.get("packet_digests")
    events = scorer_manifest.get("events")
    omitted = scorer_manifest.get("omitted_events")
    records = scorer_manifest.get("history_record_identities")
    situation = scorer_manifest.get("situation")
    settings = scorer_manifest.get("model_settings")
    if (not isinstance(condition_by_packet, Mapping)
            or set(condition_by_packet.values()) != set(OPERATOR_CODEX_STRATEGY_CONDITIONS)
            or len(condition_by_packet) != 3
            or set(subject_packets) != set(condition_by_packet)
            or not isinstance(order, list) or len(order) != 3
            or set(order) != set(OPERATOR_CODEX_STRATEGY_CONDITIONS)
            or not isinstance(packet_order, list) or len(packet_order) != 3
            or set(packet_order) != set(condition_by_packet)
            or [condition_by_packet[packet_id] for packet_id in packet_order] != order
            or not isinstance(digests, Mapping) or set(digests) != set(condition_by_packet)
            or not isinstance(events, list) or not 1 <= len(events) <= 12
            or not isinstance(omitted, list) or not isinstance(records, list)
            or type(scorer_manifest.get("selection_limit")) is not int
            or not 1 <= scorer_manifest["selection_limit"] <= 12
            or len(events) > scorer_manifest["selection_limit"]
            or scorer_manifest.get("selection_policy") !=
                "operator_declared_unverified_relation_then_recency_then_event_id:v1"
            or not isinstance(situation, Mapping)
            or scorer_manifest.get("situation_digest") != digest(situation)
            or preregistration.get("condition_by_packet_id") != condition_by_packet
            or not isinstance(packet_order, list) or len(packet_order) != 3
            or set(packet_order) != set(condition_by_packet)
            or [condition_by_packet[packet_id] for packet_id in packet_order] != order
            or preregistration.get("packet_digests") != digests
            or preregistration.get("history_record_identities") != records
            or preregistration.get("selected_event_identities") != [
                {"event_id": item.get("attribution", {}).get("attribution_id"),
                    "event_digest": item.get("attribution", {}).get("attribution_digest")}
                for item in events]
            or preregistration.get("omitted_event_identities") != omitted
            or preregistration.get("situation_digest") != scorer_manifest.get("situation_digest")
            or preregistration.get("model_settings") != settings
            or preregistration.get("decision_quality_preregistration") !=
                scorer_manifest.get("decision_quality_preregistration")
            or not isinstance(settings, Mapping)):
        raise EmbodiedConsequenceError("operator_multi_event_preregistration_mismatch")
    if any(not isinstance(row, Mapping) or set(row) != {"record_id", "record_digest"}
            or not isinstance(row.get("record_id"), str) or not row["record_id"]
            or not isinstance(row.get("record_digest"), str) or not row["record_digest"]
            for row in records):
        raise EmbodiedConsequenceError("operator_multi_event_record_identity_invalid")
    record_digests = {row["record_id"]: row["record_digest"] for row in records}
    if len(record_digests) != len(records):
        raise EmbodiedConsequenceError("operator_multi_event_record_identity_invalid")
    event_ids: set[str] = set()
    requested_at = _time(str(situation.get("requested_at", "")))
    for item in events:
        if (not isinstance(item, Mapping)
                or set(item) != {"attribution", "source_record_id", "source_record_digest",
                    "source_fact_id", "applicability"}
                or item.get("source_record_id") not in record_digests
                or item.get("source_record_digest") != record_digests.get(item.get("source_record_id"))
                or not isinstance(item.get("source_fact_id"), str) or not item["source_fact_id"]):
            raise EmbodiedConsequenceError("operator_multi_event_source_identity_invalid")
        attribution = item.get("attribution")
        if not isinstance(attribution, Mapping):
            raise EmbodiedConsequenceError("operator_multi_event_source_identity_invalid")
        _verify_consequence_attribution(attribution)
        event_id = attribution["attribution_id"]
        if _time(attribution["evaluated_at"]) >= requested_at:
            raise EmbodiedConsequenceError("operator_multi_event_source_not_historical")
        if event_id in event_ids:
            raise EmbodiedConsequenceError("operator_multi_event_duplicate_source_event")
        event_ids.add(event_id)
        applicability = item.get("applicability")
        required_applicability_fields = {"event_id", "event_digest", "situation_digest",
            "relation", "posture", "declared_by", "declared_at", "rationale", "declaration_digest"}
        if (not isinstance(applicability, Mapping)
                or set(applicability) != required_applicability_fields
                or applicability.get("event_id") != event_id
                or applicability.get("event_digest") != attribution["attribution_digest"]
                or applicability.get("situation_digest") != scorer_manifest.get("situation_digest")
                or applicability.get("posture") not in {
                    "operator_declared_unverified", "unresolved", "not_applicable"}
                or applicability.get("declaration_digest") != digest({key:value for key,value in applicability.items()
                    if key != "declaration_digest"})):
            raise EmbodiedConsequenceError("operator_multi_event_applicability_identity_invalid")
    expected_quality_preregistration = build_strategy_decision_quality_preregistration(
        situation=situation, events=events)
    if scorer_manifest.get("decision_quality_preregistration") != expected_quality_preregistration:
        raise EmbodiedConsequenceError("strategy_decision_quality_preregistration_mismatch")
    if any(not isinstance(row, Mapping)
            or set(row) != {"source_record_id", "source_record_digest", "source_fact_id",
                "event_id", "event_digest", "omission_reason"}
            or row.get("source_record_id") not in record_digests
            or row.get("source_record_digest") != record_digests.get(row.get("source_record_id"))
            or not isinstance(row.get("source_fact_id"), str)
            or not isinstance(row.get("event_id"), str)
            or not isinstance(row.get("event_digest"), str)
            or row.get("omission_reason") != "bounded_event_selection"
            for row in omitted):
        raise EmbodiedConsequenceError("operator_multi_event_omission_evidence_invalid")
    expected_history = [{"event_id": item["attribution"]["attribution_id"],
        "event_digest": item["attribution"]["attribution_digest"],
        "source_record_id": item["source_record_id"],
        "source_record_digest": item["source_record_digest"],
        "source_fact_id": item["source_fact_id"],
        "classification": item["attribution"]["classification"],
        "causal_attribution_posture": item["attribution"]["causal_attribution_posture"],
        "commanded_value": item["attribution"].get("commanded_value"),
        "predicted_value": item["attribution"].get("predicted_value"),
        "renderer_reported_value": item["attribution"].get("renderer_reported_value"),
        "recorded_observation": item["attribution"].get("independently_observed_value"),
        "observation_independence_posture": item["attribution"].get("observation_independence_posture"),
        "evaluated_at": item["attribution"]["evaluated_at"],
        "applicability": item["applicability"],
        "applicability_independently_verified": False} for item in events]
    for packet_id, packet in subject_packets.items():
        condition = condition_by_packet[packet_id]
        expected = expected_history if condition in {"history_present", "history_restored"} else []
        if (not isinstance(packet, Mapping)
                or set(packet) != {"schema_version", "packet_id", "model_settings", "instructions",
                    "historical_evidence", "current_situation", "proposal_schema", "authority_boundary"}
                or packet.get("schema_version") != OPERATOR_MULTI_EVENT_PACKET_SCHEMA
                or packet.get("packet_id") != packet_id or digests.get(packet_id) != digest(packet)
                or packet.get("model_settings") != settings
                or packet.get("current_situation") != situation
                or packet.get("historical_evidence") != expected):
            raise EmbodiedConsequenceError("operator_multi_event_packet_identity_mismatch")
    if not set(responses) <= set(condition_by_packet):
        raise EmbodiedConsequenceError("operator_multi_event_response_packet_unknown")
    session_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    proposals_by_condition: dict[str, EmbodiedStrategyProposal] = {}
    settings_match = True
    for packet_id, condition in condition_by_packet.items():
        response = responses.get(packet_id)
        if response is None:
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "missing_response", "proposal": None})
            continue
        if (not isinstance(response, Mapping) or set(response) - {"packet_id", "session_id",
                "timestamp", "visible_model_name", "effort_setting", "generation_settings", "raw_output"}
                or response.get("packet_id") != packet_id):
            raise EmbodiedConsequenceError("operator_multi_event_response_identity_invalid")
        session_id = response.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "session_identity_missing", "proposal": None})
            continue
        if session_id in session_ids:
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "duplicate_session_submission", "proposal": None})
            continue
        session_ids.add(session_id)
        actual_settings = {"visible_model_name": response.get("visible_model_name"),
            "effort_setting": response.get("effort_setting"),
            "generation_settings": response.get("generation_settings")}
        if actual_settings != settings:
            settings_match = False
        raw = response.get("raw_output")
        if not isinstance(raw, str) or len(raw.encode("utf-8", errors="replace")) > 16384:
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "missing_or_oversized_output", "proposal": None})
            continue
        try:
            parsed = json.loads(raw, object_pairs_hook=_unique_strategy_object)
        except (ValueError, TypeError):
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "malformed_or_duplicate_key_json", "proposal": None,
                "raw_output_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()})
            continue
        if (not isinstance(parsed, Mapping)
                or set(parsed) != set(STRATEGY_PROMPT_SCHEMA["proposal_fields"])):
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "malformed_proposal_schema", "proposal": None,
                "raw_output_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()})
            continue
        try:
            proposal = make_strategy_proposal(**{**dict(parsed),
                "relevant_consequence_ids": tuple(parsed["relevant_consequence_ids"]),
                "factual_assertions": tuple(parsed["factual_assertions"])})
            verify_strategy_proposal(proposal,
                situation_binding=situation["situation_binding"],
                body_generation=situation["body_generation"])
        except (EmbodiedConsequenceError, KeyError, TypeError, ValueError):
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "malformed_or_mismatched_proposal", "proposal": None,
                "raw_output_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()})
            continue
        proposals_by_condition[condition] = proposal
        quality_result = score_strategy_decision_quality(proposal=proposal,
            situation=situation, events=events,
            preregistration=scorer_manifest["decision_quality_preregistration"])
        rows.append({"packet_id": packet_id, "condition": condition,
            "status": "proposal_parsed", "proposal": proposal.semantic_payload(),
            "proposal_digest": proposal.strategy_digest,
            "decision_quality": quality_result,
            "raw_output_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "session_id": session_id,
            "timestamp": response.get("timestamp")})
    conditions_complete = set(proposals_by_condition) == set(OPERATOR_CODEX_STRATEGY_CONDITIONS)
    event_score = None
    if conditions_complete and settings_match:
        event_score = score_strategy_experiment(proposals=tuple(
            proposals_by_condition[name] for name in OPERATOR_CODEX_STRATEGY_CONDITIONS),
            consequence_events=events, situation=situation)
    status = "scored" if event_score is not None else "partial_or_incomparable"
    result = {"schema_version": "sentientos.operator_codex_strategy_multi_event_scores:v1",
        "status": status, "scoreable_task_fraction": {"numerator": int(event_score is not None),
            "denominator": 1}, "conditions_complete": conditions_complete,
        "subject_settings_comparable": settings_match,
        "condition_results": rows, "event_score": event_score,
        "selected_event_identities": preregistration["selected_event_identities"],
        "omitted_event_identities": preregistration["omitted_event_identities"],
        "improvement_claimed": False, "authority": dict(FALSE_AUTHORITY)}
    result["score_digest"] = digest(result)
    return result


def score_operator_codex_strategy_responses(*, scorer_manifest: Mapping[str, Any],
        preregistration: Mapping[str, Any], subject_packets: Mapping[str, Mapping[str, Any]],
        responses: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Validate external strategy outputs and reuse the canonical independent strategy scorer."""
    if (not isinstance(scorer_manifest, Mapping)
            or set(scorer_manifest) != {"schema_version", "condition_by_packet_id", "condition_order",
                "packet_digests", "history_record", "source_consequence", "history_projection",
                "situation", "situation_digest", "model_settings", "source_record_identity",
                "scoring_method", "interpretation_limits"}
            or scorer_manifest.get("schema_version") != "sentientos.operator_codex_strategy_scorer:v1"
            or not isinstance(preregistration, Mapping)
            or set(preregistration) != {"schema_version", "packet_ids_in_randomized_order",
                "condition_by_packet_id", "packet_digests", "history_record_identity",
                "situation_digest", "model_settings", "custody_note"}
            or preregistration.get("schema_version") != "sentientos.operator_codex_strategy_preregistration:v1"
            or not isinstance(responses, Mapping) or not isinstance(subject_packets, Mapping)):
        raise EmbodiedConsequenceError("operator_strategy_scorer_manifest_invalid")
    condition_by_packet = scorer_manifest.get("condition_by_packet_id")
    digests = scorer_manifest.get("packet_digests")
    order = preregistration.get("packet_ids_in_randomized_order")
    if (not isinstance(condition_by_packet, Mapping)
            or any(not isinstance(value, str) for value in condition_by_packet.values())
            or set(condition_by_packet.values())
            != set(OPERATOR_CODEX_STRATEGY_CONDITIONS)
            or any(not isinstance(packet_id, str) or len(packet_id) != 24
                or any(character not in "0123456789abcdef" for character in packet_id)
                for packet_id in condition_by_packet)
            or not isinstance(digests, Mapping) or set(digests) != set(condition_by_packet)
            or set(subject_packets) != set(condition_by_packet)
            or preregistration.get("condition_by_packet_id") != condition_by_packet
            or preregistration.get("packet_digests") != digests
            or scorer_manifest.get("source_record_identity")
                != preregistration.get("history_record_identity")
            or scorer_manifest.get("situation_digest") != preregistration.get("situation_digest")
            or scorer_manifest.get("model_settings") != preregistration.get("model_settings")
            or not isinstance(order, list) or len(order) != len(condition_by_packet)
            or set(order) != set(condition_by_packet)
            or [condition_by_packet[packet_id] for packet_id in order]
                != scorer_manifest.get("condition_order")):
        raise EmbodiedConsequenceError("operator_strategy_preregistration_mismatch")
    history_record = scorer_manifest.get("history_record")
    consequence = scorer_manifest.get("source_consequence")
    if (not isinstance(history_record, Mapping) or not isinstance(consequence, Mapping)
            or _strategy_prior_consequence_binding(history_record, consequence).get("posture")
                != "verified_prior_selected_history"):
        raise EmbodiedConsequenceError("operator_strategy_source_history_invalid")
    record_semantic = dict(history_record)
    record_semantic.pop("record_id", None)
    record_digest = record_semantic.pop("record_digest", None)
    calculated_record_digest = digest(record_semantic)
    if (record_digest != calculated_record_digest
            or history_record.get("record_id") != "devrec-" + calculated_record_digest[7:31]
            or history_record.get("epistemic_posture") != "historical_interpretation_not_current_truth"
            or history_record.get("current_truth") is not False
            or history_record.get("authority") is not False
            or history_record.get("policy") is not False):
        raise EmbodiedConsequenceError("operator_strategy_source_record_identity_invalid")
    for packet_id, packet in subject_packets.items():
        condition = condition_by_packet[packet_id]
        expected_history = ([scorer_manifest["history_projection"]]
            if condition in {"history_present", "history_restored"} else [])
        if (not isinstance(packet, Mapping)
                or set(packet) != {"schema_version", "packet_id", "model_settings", "instructions",
                    "historical_evidence", "current_situation", "proposal_schema",
                    "authority_boundary", "factual_assertion_contract"}
                or digests.get(packet_id) != digest(packet)
                or packet.get("schema_version") != OPERATOR_CODEX_STRATEGY_PACKET_SCHEMA
                or packet.get("packet_id") != packet_id
                or packet.get("current_situation") != scorer_manifest.get("situation")
                or packet.get("model_settings") != scorer_manifest.get("model_settings")
                or packet.get("historical_evidence") != expected_history):
            raise EmbodiedConsequenceError("operator_strategy_packet_digest_mismatch")
    if any(not isinstance(value, Mapping) or value.get("packet_id") != packet_id
            for packet_id, value in responses.items()
            if packet_id in condition_by_packet):
        raise EmbodiedConsequenceError("operator_strategy_response_packet_binding_mismatch")
    if not set(responses) <= set(condition_by_packet):
        raise EmbodiedConsequenceError("operator_strategy_response_packet_unknown")
    response_fields = {"packet_id", "session_id", "timestamp", "visible_model_name",
        "effort_setting", "generation_settings", "raw_output"}
    if any(not set(response) <= response_fields for response in responses.values()):
        raise EmbodiedConsequenceError("operator_strategy_response_record_schema_invalid")
    settings = scorer_manifest["model_settings"]
    by_condition: dict[str, EmbodiedStrategyProposal] = {}
    rows: list[dict[str, Any]] = []
    seen_sessions: set[str] = set()
    def response_evidence(response: Mapping[str, Any] | None) -> dict[str, Any]:
        raw = response.get("raw_output") if isinstance(response, Mapping) else None
        raw_bytes = raw.encode("utf-8", errors="replace") if isinstance(raw, str) else b""
        return {"raw_output": raw if isinstance(raw, str) and len(raw_bytes) <= 16384 else None,
            "raw_output_bytes": len(raw_bytes),
            "raw_output_sha256": hashlib.sha256(raw_bytes).hexdigest() if isinstance(raw, str) else None,
            "session_record": ({key: response.get(key) for key in (
                "session_id", "timestamp", "visible_model_name", "effort_setting",
                "generation_settings")} if isinstance(response, Mapping) else None)}
    for packet_id, condition in condition_by_packet.items():
        response = responses.get(packet_id)
        if response is None:
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "interrupted_or_not_run", "proposal": None,
                **response_evidence(None)})
            continue
        session_id = response.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "session_identity_missing", "proposal": None,
                **response_evidence(response)})
            continue
        if session_id in seen_sessions:
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "duplicate_session_submission", "proposal": None,
                **response_evidence(response)})
            continue
        seen_sessions.add(session_id)
        raw = response.get("raw_output")
        if not isinstance(raw, str) or len(raw.encode("utf-8", errors="replace")) > 16384:
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "missing_or_oversized_output", "proposal": None,
                **response_evidence(response)})
            continue
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            status = "partial_output" if raw.strip().startswith("{") and not raw.strip().endswith("}") else "malformed_json"
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": status, "proposal": None, **response_evidence(response)})
            continue
        if (not isinstance(parsed, Mapping)
                or set(parsed) != set(STRATEGY_PROMPT_SCHEMA["proposal_fields"])):
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "malformed_proposal_schema", "proposal": None,
                **response_evidence(response)})
            continue
        bool_fields = ("retry_prior_strategy", "alter_body_or_rig", "more_observation_required",
            "distinguishes_renderer_and_observer")
        if any(type(parsed.get(key)) is not bool for key in bool_fields):
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "malformed_boolean_field", "proposal": None,
                **response_evidence(response)})
            continue
        if (type(parsed.get("body_generation")) is not int
                or parsed.get("situation_binding") != scorer_manifest["situation"].get("situation_binding")
                or not isinstance(parsed.get("relevant_consequence_ids"), list)
                or not isinstance(parsed.get("factual_assertions"), list)
                or any(not isinstance(item, str) for item in parsed["relevant_consequence_ids"])
                or any(not isinstance(item, Mapping) for item in parsed["factual_assertions"])):
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "malformed_proposal_fields", "proposal": None,
                **response_evidence(response)})
            continue
        claim_kinds = {"historical_event", "renderer_report", "independent_observation",
            "physical_execution", "causal_attribution", "other"}
        if any(set(assertion) - {"claim_kind", "claim", "source_id", "source_digest"}
                or not isinstance(assertion.get("claim_kind"), str)
                or assertion.get("claim_kind") not in claim_kinds
                or not isinstance(assertion.get("claim"), str)
                or len(assertion.get("claim", "")) > 512
                or ("source_id" in assertion and (not isinstance(assertion.get("source_id"), str)
                    or not assertion.get("source_id")))
                or ("source_digest" in assertion and (not isinstance(assertion.get("source_digest"), str)
                    or not assertion.get("source_digest")))
                for assertion in parsed["factual_assertions"]):
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "malformed_factual_assertion", "proposal": None,
                **response_evidence(response)})
            continue
        try:
            proposal = make_strategy_proposal(**{**dict(parsed),
                "relevant_consequence_ids": tuple(parsed["relevant_consequence_ids"]),
                "factual_assertions": tuple(parsed["factual_assertions"])})
            verify_strategy_proposal(proposal,
                situation_binding=str(scorer_manifest["situation"]["situation_binding"]),
                body_generation=int(scorer_manifest["situation"]["body_generation"]))
        except (EmbodiedConsequenceError, TypeError, ValueError):
            rows.append({"packet_id": packet_id, "condition": condition,
                "status": "malformed_or_invalid_proposal", "proposal": None,
                **response_evidence(response)})
            continue
        by_condition[condition] = proposal
        claim_audit = []
        for assertion in proposal.factual_assertions:
            kind = assertion["claim_kind"]
            known_identity = ({"source_id": consequence.get("attribution_id"),
                "source_digest": consequence.get("attribution_digest")}
                if kind in {"historical_event", "causal_attribution", "physical_execution"}
                else {"source_id": consequence.get("renderer_report_id"),
                    "source_digest": consequence.get("renderer_report_digest")}
                    if kind == "renderer_report"
                    else {"source_id": consequence.get("observation_id"),
                        "source_digest": consequence.get("observation_digest")}
                        if kind == "independent_observation" else {})
            unsupported = (kind == "physical_execution"
                or (kind == "independent_observation"
                    and consequence.get("observation_independence_posture")
                        != "verified_independent_observation")
                or (kind == "causal_attribution"
                    and consequence.get("causal_attribution_posture")
                        in {"external_interference_possible", "causal_attribution_insufficient"}))
            renderer_confusion = (kind == "independent_observation"
                and assertion.get("source_id") == consequence.get("renderer_report_id"))
            claim_audit.append({"claim_kind": kind,
                "source_binding_matches_known_event": (
                    assertion.get("source_id") == known_identity.get("source_id")
                    and assertion.get("source_digest") == known_identity.get("source_digest"))
                    if assertion.get("source_id") is not None else None,
                "unsupported_under_recorded_evidence": unsupported,
                "renderer_report_confused_with_independent_observation": renderer_confusion,
                "claim_semantics_independently_verified": False})
        actual_settings = {key: response.get(key) for key in (
            "visible_model_name", "effort_setting", "generation_settings")}
        rows.append({"packet_id": packet_id, "condition": condition, "status": "scored_candidate",
            "proposal": asdict(proposal), "session_id": session_id,
            "timestamp": response.get("timestamp"),
            "reported_settings_match_preregistration": actual_settings == settings,
            "factual_assertion_audit": claim_audit,
            **response_evidence(response)})
    if len(by_condition) != len(OPERATOR_CODEX_STRATEGY_CONDITIONS):
        scoring = {"status": "not_scored_incomplete_or_unscoreable_subject_set",
            "authority": dict(FALSE_AUTHORITY)}
    elif any(row.get("reported_settings_match_preregistration") is not True for row in rows):
        scoring = {"status": "not_scored_incomparable_subject_settings",
            "authority": dict(FALSE_AUTHORITY)}
    else:
        scoring = score_strategy_experiment(proposals=tuple(
            by_condition[condition] for condition in OPERATOR_CODEX_STRATEGY_CONDITIONS),
            consequence=consequence)
        scoring["status"] = "scored"
    semantic = {"schema_version": "sentientos.operator_codex_strategy_scores:v1",
        "source_record_identity": scorer_manifest["source_record_identity"],
        "situation_digest": scorer_manifest["situation_digest"],
        "conditions": rows, "strategy_scoring": scoring,
        "submitted_proposal_count": sum(row["status"] == "scored_candidate" for row in rows),
        "subject_session_posture": "operator_reported_external_sessions_not_independently_verified",
        "model_settings_independently_verified": False,
        "execution_authority": dict(FALSE_AUTHORITY)}
    semantic["score_digest"] = digest(semantic)
    return semantic

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
                              and (history_record.get("epistemic_posture")
                                  or history_record["candidate"].get("epistemic_posture"))
                                  =="historical_interpretation_not_current_truth"
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
        scoring = score_strategy_experiment(proposals=proposals, consequence=consequence,
            resource_evidence_bindings=evidence_scope.get("resource_bindings", ()))
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
    if (claimed_id!=expected_id or claimed_digest!=expected_digest
            or dict(value.get("authority",{}))!=dict(FALSE_AUTHORITY)
            or value.get("effect_proven") is not False
            or value.get("proven_consequence_value") is not None
            or value.get("classification") not in ATTRIBUTION_RESULTS
            or value.get("causal_attribution_posture") not in CAUSAL_POSTURES
            or value.get("observation_independence_posture") not in {
                "unverified_caller_assertion", "no_observation"}):
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
    selected_sources = candidate.get("selected_sources") if isinstance(candidate, Mapping) else None
    if not isinstance(selected_sources, (tuple, list)) or len(selected_sources) > 16:
        return {"posture":"selected_history_source_bindings_unavailable",
            "attribution_id":consequence.get("attribution_id"),
            "attribution_digest":consequence.get("attribution_digest")}
    source_by_id = {str(item.get("source_id")): item for item in selected_sources
        if isinstance(item, Mapping) and isinstance(item.get("source_id"), str)}
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
        source_binding = source_by_id.get(str(attribution_id))
        if (source.get("schema_version") != consequence.get("schema_version")
                or source.get("kind") not in {"embodiment", "fulfillment"}
                or not isinstance(source_binding, Mapping)
                or source_binding.get("digest") != source.get("digest")
                or source_binding.get("kind") != source.get("kind")):
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
        if source.get("kind")!="resource_governor":
            continue
        subject_kind = subject.get("subject_kind")
        if subject_kind in {"strategy_invocation_resource_lineage",
                            "model_replacement_invocation_resource_lineage"}:
            linkage=payload.get("resource_linkage")
            resource_record=payload.get("resource_record")
            allocation=payload.get("allocation_identity")
            if not all(isinstance(value,Mapping) for value in (linkage,resource_record,allocation)):
                verified=False
                continue
            receipts=linkage.get("consumption_receipt_digests")
            linkage_body={"receipt_digest":linkage.get("effect_receipt_digest"),
                "allocation_digest":linkage.get("allocation_digest"),
                "attempt_id":linkage.get("attempt_id"),
                "consumption_receipt_digests":tuple(receipts) if isinstance(receipts,(list,tuple)) else ()}
            linkage_digest=hashlib.sha256(canonical_bytes(linkage_body)).hexdigest()
            allocation_binding={key:allocation.get(key) for key in (
                "allocation_id", "allocation_digest", "principal_id",
                "principal_binding_digest", "principal_epoch", "resource_kind",
                "epoch", "policy_digest")}
            request_context=payload.get("task_context")
            if isinstance(request_context,Mapping):
                context_value=dict(request_context)
                context_digest=digest(context_value)
                if len(canonical_bytes(context_value))<=8192:
                    context_binding={
                        "posture":"recorded_experiment_context_not_sponsorship",
                        "context_digest":context_digest,
                        "experiment_condition":context_value.get("experiment_condition"),
                        "experiment_protocol_id":context_value.get("experiment_protocol_id"),
                        "history_record_ids_digest":digest(list(context_value.get(
                            "history_record_ids",()))) if isinstance(context_value.get(
                                "history_record_ids"), (list,tuple)) else None,
                        "history_record_count":len(context_value.get("history_record_ids",()))
                            if isinstance(context_value.get("history_record_ids"), (list,tuple)) else None,
                        "history_record_digests_digest":digest(list(context_value.get(
                            "history_record_digests",()))) if isinstance(context_value.get(
                                "history_record_digests"), (list,tuple)) else None,
                        "history_record_digest_count":len(context_value.get(
                            "history_record_digests",())) if isinstance(context_value.get(
                                "history_record_digests"), (list,tuple)) else None,
                    }
                else:
                    context_binding={"posture":"recorded_context_digest_only_not_sponsorship",
                        "context_digest":context_digest}
            else:
                context_binding={"posture":"task_context_not_bound_by_source",
                    "context_digest":None}
            binding={"fact_id":fact.get("fact_id"),"source_id":source.get("source_id"),
                "source_digest":source.get("digest"),"lineage_subject_kind":subject_kind,
                "resource_record_source_id":resource_record.get("source_id"),
                "resource_record_digest":resource_record.get("record_digest"),
                "ledger_digest":resource_record.get("ledger_digest"),
                "principal_id":payload.get("principal_id"),
                "principal_binding_digest":payload.get("principal_binding_digest"),
                "allocation_identity":allocation_binding,
                "task_context":context_binding,
                "allocation_digest":allocation.get("allocation_digest"),
                "attempt_id":linkage.get("attempt_id"),
                "invocation_receipt_id":payload.get("invocation_receipt_id"),
                "invocation_receipt_digest":linkage.get("effect_receipt_digest"),
                "invocation_receipt_binding_consistent":(
                    payload.get("invocation_receipt_id")==linkage.get("effect_receipt_id")
                    and payload.get("invocation_receipt_digest")==linkage.get("effect_receipt_digest")),
                "consumption_receipt_digests":tuple(receipts) if isinstance(receipts,(list,tuple)) else (),
                "model_attribution":payload.get("model_attribution"),
                "cognitive_model_id":(
                    payload.get("model_attribution", {}).get("model_id")
                    if isinstance(payload.get("model_attribution"), Mapping) else None),
                "invocation_model_id":(
                    payload.get("model_attribution", {}).get("invocation_model_id",
                        payload.get("model_attribution", {}).get("model_id"))
                    if isinstance(payload.get("model_attribution"), Mapping) else None),
                "software_attribution":payload.get("software_attribution"),
                "event_times":tuple(payload.get("event_times",())) if isinstance(payload.get("event_times",()),(list,tuple)) else (),
                "history_context_posture":payload.get("lineage_projection_posture"),
                "lineage_posture":"verified" if fact.get("disposition")=="verified" else "incomplete",
                "lineage_findings":tuple(payload.get("lineage_findings",()))}
            resource_facts.append(binding)
            lineage_invalid=(fact.get("disposition")!="verified" or binding["lineage_findings"]
                    or payload.get("lineage_projection_posture") not in {"complete","bounded_context_incomplete"}
                    or not source.get("digest") or not resource_record.get("source_id")
                    or not resource_record.get("record_digest") or not resource_record.get("ledger_digest")
                    or not payload.get("principal_id") or not payload.get("principal_binding_digest")
                    or not isinstance(allocation_binding.get("allocation_id"),str)
                    or not allocation_binding.get("allocation_id")
                    or not binding["invocation_receipt_binding_consistent"]
                    or not linkage.get("allocation_digest") or not linkage.get("attempt_id")
                    or not linkage.get("effect_receipt_id") or not linkage.get("effect_receipt_digest")
                    or not isinstance(receipts,(list,tuple)) or not receipts or len(receipts)>16
                    or any(not isinstance(item,str) or not item for item in receipts)
                    or len(receipts)!=len(set(receipts))
                    or linkage.get("linkage_digest")!=linkage_digest
                    or allocation.get("allocation_digest")!=linkage.get("allocation_digest")
                    or allocation.get("principal_id")!=payload.get("principal_id")
                    or allocation.get("principal_binding_digest")!=payload.get("principal_binding_digest"))
            if lineage_invalid:
                binding["lineage_posture"]="incomplete"
                verified=False
            model=payload.get("model_attribution")
            if (not isinstance(model,Mapping) or not model.get("model_id")
                    or not model.get("model_artifact_digest")
                    # The governed invocation joins on the authority-map
                    # record id. Developmental model-replacement evidence
                    # separately retains its semantic cognitive/catalog id.
                    # Legacy strategy records have no separate invocation id,
                    # so their historical model_id remains the join key.
                    or model.get("invocation_model_id", model.get("model_id"))
                        !=linkage.get("model_id")
                    or model.get("model_artifact_digest")!=linkage.get("model_artifact_digest")):
                binding["lineage_posture"]="incomplete"
                verified=False
            if subject_kind=="model_replacement_invocation_resource_lineage":
                succession_values=(payload.get("model_replacement_run_id"),
                    payload.get("model_replacement_run_digest"),
                    payload.get("model_replacement_source_record_id"),
                    payload.get("model_replacement_source_record_digest"),
                    payload.get("model_replacement_condition"),payload.get("model_identity_digest"),
                    payload.get("model_provenance_manifest_digest"),payload.get("causal_context_id"),
                    payload.get("causal_context_digest"))
                binding["succession_lineage"]={"run_id":succession_values[0],
                    "run_digest":succession_values[1],"source_record_id":succession_values[2],
                    "source_record_digest":succession_values[3],"condition":succession_values[4],
                    "model_identity_digest":succession_values[5],
                    "model_provenance_manifest_digest":succession_values[6],
                    "causal_context_id":succession_values[7],"causal_context_digest":succession_values[8],
                    "software_attribution":payload.get("software_attribution")}
                if not all(isinstance(value,str) and value for value in succession_values):
                    binding["lineage_posture"]="incomplete"
                    verified=False
            continue
        if subject_kind!="causal_resource_consumption":
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
        lineage_invalid=(binding["lineage_posture"]!="verified" or binding["recovery_posture"]!="reconciled_or_restored"
                or payload.get("retention_posture")!="complete"
                or payload.get("interpretation_projection_posture")!="complete"
                or not binding["source_digest"] or not binding["ledger_digest"])
        if lineage_invalid:
            binding["lineage_posture"]="incomplete"
            verified=False
    if not resource_facts:
        posture="no_resource_evidence_in_selected_record"
    elif not verified:
        posture="resource_evidence_lineage_incomplete"
    elif len(resource_facts)!=len(facts):
        posture="mixed_selected_history"
    elif any(item.get("lineage_subject_kind") for item in resource_facts):
        posture=("resource_invocation_lineage_history_context_bounded"
            if any(item.get("history_context_posture")!="complete" for item in resource_facts)
            else "resource_invocation_lineage_history")
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
    history_fields = {"developmental_history_intervention_runs"}
    schema = config.get("schema_version")
    fields = base_fields | (review_fields if schema in {
        WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V2, WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V3} else set())
    if schema == WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V3:
        fields |= fulfillment_fields
    if schema == WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V4:
        fields |= review_fields | fulfillment_fields | history_fields
    if (set(config) != fields or config.get("schema_version") != WORLD_STATE_PROJECTION_CONFIG_SCHEMA
            and config.get("schema_version") != WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V2
            and config.get("schema_version") != WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V3
            and config.get("schema_version") != WORLD_STATE_PROJECTION_CONFIG_SCHEMA_V4
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
                    or config.get("fulfillment_receipt_ids", []) != [])
                or config.get("developmental_history_intervention_runs", []) != []):
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
    developmental_runs = config.get("developmental_history_intervention_runs", [])
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
            or not isinstance(developmental_runs, list) or len(developmental_runs) > 32
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
    if developmental_runs:
        prefix = "devexp-run-"
        seen_developmental_runs: set[str] = set()
        for item in developmental_runs:
            if (not isinstance(item, Mapping) or set(item) != {"run_id", "run_digest"}
                    or not isinstance(item.get("run_id"), str)
                    or not item["run_id"].startswith(prefix)
                    or len(item["run_id"]) != len(prefix) + 24
                    or any(character not in "0123456789abcdef" for character in item["run_id"][len(prefix):])
                    or not isinstance(item.get("run_digest"), str)
                    or len(item["run_digest"]) != 71 or not item["run_digest"].startswith("sha256:")
                    or any(character not in "0123456789abcdef" for character in item["run_digest"][7:])
                    or item["run_id"] != prefix + item["run_digest"][7:31]
                    or item["run_id"] in seen_developmental_runs):
                raise EmbodiedConsequenceError("developmental_history_projection_run_invalid")
            seen_developmental_runs.add(item["run_id"])
    # A consequence chain produces at most seven records (expectation, handoff,
    # optional renderer report, optional independent observation, attribution,
    # comparison, and chain summary). Reserve an explicit aggregate budget so
    # the World-State builder cannot silently truncate selected evidence.
    projected_record_bound = (7 * len(chain_ids) + len(identities) + len(replacement_runs)
        + len(developmental_runs) + len(review_ids) + len(fulfillment_ids))
    if projected_record_bound > MAX_WORLD_STATE_PROJECTION_RECORDS:
        raise EmbodiedConsequenceError("world_state_projection_record_budget_exceeded")
    if (not identities and not chain_ids and not replacement_runs and not developmental_runs
            and not review_ids and not fulfillment_ids):
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
        elif os.name == "nt":
            try:
                verify_explicit_directory(selected)
            except WindowsHandleCustodyError as exc:
                if str(exc) == "explicit_file_missing":
                    raise EmbodiedConsequenceError("consequence_store_root_missing") from exc
                raise EmbodiedConsequenceError("consequence_store_root_invalid") from exc
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
            event_times = {
                "expectation_created_at": expectation.created_at,
                "commanded_at": chain["handoff"].get("commanded_at"),
                "renderer_started_at": report.started_at if report is not None else None,
                "renderer_completed_at": report.completed_at if report is not None else None,
                "claimed_observation_at": observation.observed_at if observation is not None else None,
                "comparison_evaluated_at": chain["attribution"].get("evaluated_at"),
            }
            chain_record: dict[str, Any] = {
                "source_kind": "embodiment", "source_id": chain_id,
                "schema_version": CONSEQUENCE_CHAIN_SCHEMA, "subject_id": chain_id,
                "subject_kind": "embodied_consequence_chain", "stage": "observation",
                "disposition": "recorded", "evidence_strength": "digest_bound_consequence_chain",
                # World-State treats top-level observed_at as nonsemantic
                # metadata. Keep the claimed observation time only in the
                # digest-bound event_times payload below.
                "observed_at": None,
                "payload": {"chain_id": chain_id, "chain_digest": chain["chain_digest"],
                    "component_source_ids": [item["source_id"] for item in chain_records],
                    "component_record_digests": [item["digest"] for item in chain_records],
                    "event_times": event_times,
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
            proposal_occurrences: dict[tuple[str, str], int] = {}
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
                proposal_key = (proposal.strategy_id, proposal.strategy_digest)
                occurrence = proposal_occurrences.get(proposal_key, 0)
                if occurrence >= len(matching_statuses):
                    raise EmbodiedConsequenceError("stored_strategy_experiment_proposal_status_invalid")
                # Repeated semantic proposals are legitimate experimental
                # outcomes (notably history_present == history_restored).
                # Bind each occurrence to its ordered condition status rather
                # than treating a repeated proposal identity as ambiguous.
                proposal_status = matching_statuses[occurrence]
                proposal_occurrences[proposal_key] = occurrence + 1
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
                    "source_id":f"strategy-experiment-proposal:{identity}:{condition}:{proposal.strategy_id}",
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
            proposal_occurrences: dict[tuple[str, str], int] = {}
            for raw in proposals:
                if not isinstance(raw, Mapping):
                    raise EmbodiedConsequenceError("stored_strategy_experiment_proposal_invalid")
                proposal = _strategy_proposal_from_mapping(raw)
                matches = [item for item in statuses if isinstance(item, Mapping)
                    and item.get("proposal_id") == proposal.strategy_id
                    and item.get("proposal_digest") == proposal.strategy_digest]
                proposal_key = (proposal.strategy_id, proposal.strategy_digest)
                occurrence = proposal_occurrences.get(proposal_key, 0)
                if occurrence >= len(matches) or matches[occurrence].get("status") not in {"completed", "contradictory"}:
                    raise EmbodiedConsequenceError("stored_strategy_experiment_proposal_status_invalid")
                status = matches[occurrence]
                proposal_occurrences[proposal_key] = occurrence + 1
                condition = status.get("condition")
                if condition not in {"history_present", "history_withheld", "history_restored"}:
                    raise EmbodiedConsequenceError("stored_strategy_experiment_proposal_status_invalid")
                execution_contexts = [item for item in projected_contexts.get(proposal_key, [])
                    if item.get("condition") == condition]
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
        # Canonical JSON custody reloads tuples as arrays. Compare their
        # canonical representation so an exact publication is not mistaken
        # for conflicting evidence merely because Python used tuple/list
        # containers on opposite sides of the durable boundary.
        if stored is None or canonical_bytes(stored) != canonical_bytes(record):
            raise EmbodiedConsequenceError("strategy_condition_terminal_conflict")
        return stored

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
