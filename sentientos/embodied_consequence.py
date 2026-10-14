Warning: truncated output (original token count: 51924)
Total output lines: 3119

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
        if key not in {"comparison_id"…36924 tokens truncated…                or not isinstance(execution_rows, list) or len(execution_rows) > len(condition_order)):
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
