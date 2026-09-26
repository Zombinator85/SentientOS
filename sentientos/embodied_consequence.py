"""Deterministic embodied consequence evidence and developmental experiments.

Every record in this module is evidence or a proposal.  Nothing here performs an
embodied action, adopts a body, grants authority, or promotes interpretation to
current truth.
"""
from __future__ import annotations

import hashlib
import json
import os
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
EXPERIMENT_RESULT_SCHEMA = "sentientos.embodied_strategy_experiment_result:v1"
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
    _validate_authority(raw.authority)
    if raw.uncertainty not in {"low","medium","high","unknown"} or len(raw.rationale)>2000:
        raise EmbodiedConsequenceError("strategy_proposal_invalid")
    sid,dg=_identity("strategy",raw.semantic_payload()); return replace(raw,strategy_id=sid,strategy_digest=dg)


class StrategyCognitionBackend(Protocol):
    def propose(self, *, condition: str, history: Sequence[Mapping[str, Any]], situation: Mapping[str, Any]) -> EmbodiedStrategyProposal: ...


def score_strategy_experiment(*, proposals: Sequence[EmbodiedStrategyProposal], consequence: Mapping[str, Any]) -> dict[str, Any]:
    if len(proposals)!=3: raise EmbodiedConsequenceError("strategy_condition_count_invalid")
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
    if set(protocol)!=required: raise EmbodiedConsequenceError("strategy_protocol_shape_invalid")
    record_digest=history_record.get("record_digest")
    conditions=("history_present","history_withheld","history_restored")
    proposals=[]
    for condition in conditions:
        history=() if condition=="history_withheld" else (history_record,)
        proposals.append(backend.propose(condition=condition,history=history,situation=situation))
    scoring=score_strategy_experiment(proposals=proposals,consequence=consequence)
    payload={"schema_version":EXPERIMENT_RESULT_SCHEMA,"protocol":dict(protocol),"protocol_digest":digest(protocol),
        "condition_order":list(conditions),"withheld_record_id":history_record.get("record_id"),"withheld_record_digest":record_digest,
        "proposals":[asdict(p) for p in proposals],"scoring":scoring,"no_retries":True,"improvement_claimed":False,"authority":dict(FALSE_AUTHORITY)}
    payload["experiment_result_id"],payload["experiment_result_digest"]=_identity("strategy-experiment",payload)
    return payload


class ConsequenceStore:
    """Immutable exact-chain store for consequence and experiment artifacts."""
    def __init__(self, root: Path) -> None: self.root=Path(root)
    def put(self, kind: str, identity: str, value: Mapping[str, Any]) -> Path:
        path=self.root/kind/f"{identity}.json"; path.parent.mkdir(parents=True,exist_ok=True)
        data=canonical_bytes(value)+b"\n"
        if path.exists():
            if path.read_bytes()!=data: raise EmbodiedConsequenceError("artifact_identity_collision")
            return path
        fd,temp=tempfile.mkstemp(dir=path.parent,prefix=".consequence-")
        try:
            with os.fdopen(fd,"wb") as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp,path)
        finally:
            if os.path.exists(temp): os.unlink(temp)
        return path
    def get(self, kind: str, identity: str, *, digest_field: str) -> dict[str, Any]:
        path=self.root/kind/f"{identity}.json"
        try: value=json.loads(path.read_text())
        except (OSError,json.JSONDecodeError) as exc: raise EmbodiedConsequenceError("stored_artifact_missing_or_corrupt") from exc
        claimed=value.get(digest_field); semantic=dict(value); semantic.pop(digest_field,None)
        id_fields={"expectation_digest":"expectation_id","report_digest":"report_id","observation_digest":"observation_id",
                   "attribution_digest":"attribution_id","comparison_digest":"comparison_id","experiment_result_digest":"experiment_result_id"}
        semantic.pop(id_fields[digest_field],None)
        if claimed!=digest(semantic): raise EmbodiedConsequenceError("stored_artifact_digest_mismatch")
        return cast(dict[str, Any], value)
