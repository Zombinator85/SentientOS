"""One-shot, evidence-only evaluation of an actually resident maintenance successor.

Expected consequence, validation, observation, and causal attribution are distinct.
This owner has no Git, adoption, rollback, grant, process, provider, or host authority.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

PROTOCOL_SCHEMA = "sentientos.maintenance_post_adoption_evaluation_protocol:v1"
BASELINE_SCHEMA = "sentientos.maintenance_pre_adoption_baseline:v1"
OBSERVATION_SCHEMA = "sentientos.maintenance_post_adoption_observation:v1"
EVALUATION_SCHEMA = "sentientos.maintenance_post_adoption_evaluation:v1"
ROLLBACK_SCHEMA = "sentientos.maintenance_rollback_recommendation:v1"
FALSE_AUTHORITY = {"git":False,"repository_mutation":False,"commit":False,"push":False,"pr_creation":False,
    "software_adoption":False,"process_replacement":False,"rollback":False,"grant":False,"admission":False,
    "provider_network":False,"host_actuation":False,"authority_widening":False}
COMPARATORS = frozenset({"equals","true","false","present","absent","increase","decrease","nonincrease",
    "nondecrease","numeric_tolerance","bounded_interval","set_includes","set_excludes","status_allowed"})
RESULTS = frozenset({"target_expectation_satisfied","target_expectation_contradicted","mixed_outcome",
    "new_regression_observed","no_detectable_change","insufficient_evidence","measurement_failed","indeterminate"})
ADOPTION_RECEIPT_SCHEMA = "sentientos.maintenance_resident_runtime_adoption_receipt:v2"


class PostAdoptionEvaluationError(ValueError): pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()


def digest(value: Any) -> str: return "sha256:"+hashlib.sha256(canonical_bytes(value)).hexdigest()


def _identity(prefix: str, payload: Mapping[str,Any]) -> tuple[str,str]:
    value=digest(payload); return f"{prefix}:{value[7:31]}",value


def _false(value: Mapping[str,bool]) -> None:
    if dict(value)!=FALSE_AUTHORITY: raise PostAdoptionEvaluationError("runtime_authority_must_be_all_false")


def _payload(value: Any, id_field: str, digest_field: str) -> dict[str,Any]:
    body=asdict(value); body.pop(id_field); body.pop(digest_field); return body


@dataclass(frozen=True)
class MeasurementDefinition:
    observable_id: str; source_kind: str; measurement_law: str; comparator: str; expected_value: Any
    disconfirming_value: Any; protected_invariant: bool = False; required: bool = True
    tolerance: float | None = None; lower_bound: float | None = None; upper_bound: float | None = None


@dataclass(frozen=True)
class EvaluationProtocol:
    protocol_id: str; protocol_digest: str; maintenance_task_id: str; proposal_id: str
    signal_ids: tuple[str,...]; implementation_session_id: str; validation_result_digest: str
    landed_commit: str; landed_tree: str; predecessor_generation: int; expected_successor_generation: int
    target_scope: str; measurements: tuple[MeasurementDefinition,...]; required_evidence_sources: tuple[str,...]
    observation_trigger: Mapping[str,Any]; created_at: str; creation_generation: int
    authority: Mapping[str,bool]; schema_version: str = PROTOCOL_SCHEMA

    def payload(self) -> dict[str,Any]: return _payload(self,"protocol_id","protocol_digest")


def make_protocol(**kwargs: Any) -> EvaluationProtocol:
    measurements=tuple(x if isinstance(x,MeasurementDefinition) else MeasurementDefinition(**x) for x in kwargs.pop("measurements"))
    raw=EvaluationProtocol("","",measurements=measurements,authority=dict(FALSE_AUTHORITY),**kwargs)
    _false(raw.authority)
    if (not raw.maintenance_task_id or not raw.proposal_id or not raw.implementation_session_id or
            raw.expected_successor_generation != raw.predecessor_generation+1 or not raw.measurements or
            len({m.observable_id for m in raw.measurements})!=len(raw.measurements) or
            any(m.comparator not in COMPARATORS or not m.observable_id or not m.measurement_law for m in raw.measurements)):
        raise PostAdoptionEvaluationError("evaluation_protocol_invalid")
    pid,pdg=_identity("post-adoption-protocol",raw.payload()); return replace(raw,protocol_id=pid,protocol_digest=pdg)


@dataclass(frozen=True)
class Baseline:
    baseline_id: str; baseline_digest: str; protocol_id: str; protocol_digest: str; predecessor_generation: int
    source_revision: str; source_tree: str; runtime_identity: str; observations: Mapping[str,Any]
    source_records: Mapping[str,Mapping[str,str]]; measurement_laws: Mapping[str,str]; observed_at: str
    collector_id: str; authority: Mapping[str,bool]; schema_version: str = BASELINE_SCHEMA
    def payload(self) -> dict[str,Any]: return _payload(self,"baseline_id","baseline_digest")


def make_baseline(protocol: EvaluationProtocol, **kwargs: Any) -> Baseline:
    raw=Baseline("","",protocol_id=protocol.protocol_id,protocol_digest=protocol.protocol_digest,
        predecessor_generation=protocol.predecessor_generation,authority=dict(FALSE_AUTHORITY),**kwargs)
    expected={m.observable_id:m.measurement_law for m in protocol.measurements}
    if dict(raw.measurement_laws)!=expected or set(raw.observations)-set(expected): raise PostAdoptionEvaluationError("baseline_measurement_law_mismatch")
    if raw.observed_at <= protocol.created_at: raise PostAdoptionEvaluationError("baseline_not_after_protocol")
    bid,bdg=_identity("pre-adoption-baseline",raw.payload()); return replace(raw,baseline_id=bid,baseline_digest=bdg)


@dataclass(frozen=True)
class SuccessorQualification:
    successor_generation: int; successor_commit: str; successor_tree: str; generation_digest: str
    continuity_receipt_digest: str; adoption_receipt_digest: str; launch_provenance_digest: str
    readiness_receipt_digest: str; adoption_completed_at: str; readiness_status: str


@dataclass(frozen=True)
class PostAdoptionObservation:
    observation_id: str; observation_digest: str; protocol_id: str; protocol_digest: str; baseline_digest: str
    predecessor_generation: int; successor_generation: int; predecessor_revision: str; successor_revision: str
    successor_tree: str; continuity_receipt_digest: str; adoption_receipt_digest: str
    launch_provenance_digest: str; readiness_receipt_digest: str; observations: Mapping[str,Any]
    source_records: Mapping[str,Mapping[str,str]]; measurement_laws: Mapping[str,str]; observed_at: str
    collector_id: str; authority: Mapping[str,bool]; schema_version: str = OBSERVATION_SCHEMA
    def payload(self) -> dict[str,Any]: return _payload(self,"observation_id","observation_digest")


@dataclass(frozen=True)
class Evaluation:
    evaluation_id: str; evaluation_digest: str; protocol_id: str; protocol_digest: str; task_id: str
    baseline_digest: str; observation_digest: str; predecessor_generation: int; successor_generation: int
    predecessor_revision: str; successor_revision: str; comparisons: tuple[Mapping[str,Any],...]
    missing_evidence: tuple[str,...]; contradictions: tuple[str,...]; result: str; attribution_posture: str
    evaluated_at: str; reconstruction_lineage: tuple[str,...]; validation_result_digest: str
    authority: Mapping[str,bool]; schema_version: str = EVALUATION_SCHEMA
    def payload(self) -> dict[str,Any]: return _payload(self,"evaluation_id","evaluation_digest")


@dataclass(frozen=True)
class RollbackRecommendation:
    recommendation_id: str; recommendation_digest: str; evaluation_id: str; current_generation: int
    predecessor_generation: int; predecessor_revision: str; rationale: str; urgency: str
    operator_decision_required: bool; executes_rollback: bool; authority: Mapping[str,bool]
    schema_version: str = ROLLBACK_SCHEMA


def _compare(defn: MeasurementDefinition, before: Any, after: Any) -> str:
    c=defn.comparator; expected=defn.expected_value
    try:
        met = (after==expected if c=="equals" else bool(after) is True if c=="true" else bool(after) is False if c=="false"
            else after is not None if c=="present" else after is None if c=="absent"
            else after>before if c=="increase" else after<before if c=="decrease"
            else after<=before if c=="nonincrease" else after>=before if c=="nondecrease"
            else abs(float(after)-float(expected))<=float(defn.tolerance if defn.tolerance is not None else 0) if c=="numeric_tolerance"
            else float(defn.lower_bound if defn.lower_bound is not None else after)<=float(after)<=float(defn.upper_bound if defn.upper_bound is not None else after) if c=="bounded_interval"
            else set(expected).issubset(set(after)) if c=="set_includes" else set(expected).isdisjoint(set(after)) if c=="set_excludes"
            else after in set(expected))
    except (TypeError,ValueError): return "unmeasurable"
    if met: return "expected_change_observed"
    if after==before: return "unchanged"
    if defn.disconfirming_value is not None and after==defn.disconfirming_value: return "regression_observed" if defn.protected_invariant else "expected_change_absent"
    return "expected_change_absent"


def post_adoption_epistemic_binding(*, proposition_id: str, evaluation: Evaluation, observed_at: str) -> Any:
    from sentientos.persistent_epistemic_state import make_evidence_binding
    relation="supports" if evaluation.result=="target_expectation_satisfied" else "contradicts" if evaluation.result in {"target_expectation_contradicted","new_regression_observed"} else "contextualizes"
    return make_evidence_binding(proposition_id=proposition_id,source_artifact_id=evaluation.evaluation_id,
        source_digest=evaluation.evaluation_digest,source_schema=evaluation.schema_version,
        source_class="post_adoption_evaluation",observation_time=observed_at,evidence_relation=relation,
        dependency_kind="independently_sourced_observation",dependency_group=evaluation.observation_digest,
        upstream_binding_ids=(),freshness="current",reliability_posture=relation)


def improvement_signal_record(evaluation: Evaluation) -> Mapping[str,Any] | None:
    if evaluation.result=="target_expectation_satisfied": return None
    kind="recurring_failure" if evaluation.result in {"target_expectation_contradicted","new_regression_observed","mixed_outcome"} else "telemetry_gap"
    severity="high" if evaluation.result=="new_regression_observed" else "medium"
    return {"source_kind":"post_adoption_evaluation","finding_kind":kind,"severity":severity,
        "description":f"Post-adoption result {evaluation.result} for task {evaluation.task_id}","spec_id":evaluation.task_id,
        "source_artifact":evaluation.evaluation_id,"source_digest":evaluation.evaluation_digest,
        "evidence_refs":list(evaluation.reconstruction_lineage),"observed_at":evaluation.evaluated_at,
        "declared_constraints":["proposal_only","no_repository_mutation","no_automatic_retry"]}


class MaintenancePostAdoptionEvaluationOwner:
    """Immutable explicit-root custody; each protocol/successor pair terminates once."""
    def __init__(self, root: str|Path) -> None:
        self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.root.is_symlink(): raise PostAdoptionEvaluationError("evaluation_custody_unsafe")
        for name in ("protocols","baselines","observations","evaluations","signals","recommendations"): (self.root/name).mkdir(exist_ok=True,mode=0o700)
        self.verify()

    def _write(self, kind: str, identity: str, value: Any) -> None:
        path=self.root/kind/(identity.replace(":","-")+".json"); data=canonical_bytes(asdict(value) if not isinstance(value,Mapping) else value)+b"\n"
        try: fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,"O_NOFOLLOW",0),0o600)
        except FileExistsError:
            if path.read_bytes()!=data: raise PostAdoptionEvaluationError("immutable_evaluation_record_conflict")
            return
        with os.fdopen(fd,"wb") as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())

    def _read(self, kind: str) -> list[dict[str,Any]]:
        values=[]
        for path in sorted((self.root/kind).glob("*.json")):
            if path.is_symlink(): raise PostAdoptionEvaluationError("evaluation_history_corrupt")
            try: value=json.loads(path.read_text())
            except (OSError,json.JSONDecodeError) as exc: raise PostAdoptionEvaluationError("evaluation_history_corrupt") from exc
            values.append(value)
        return values

    def preregister(self, protocol: EvaluationProtocol) -> EvaluationProtocol:
        _false(protocol.authority)
        if make_protocol(**{k:v for k,v in asdict(protocol).items() if k not in {"protocol_id","protocol_digest","schema_version","authority"}})!=protocol: raise PostAdoptionEvaluationError("protocol_digest_mismatch")
        self._write("protocols",protocol.protocol_id,protocol); return protocol

    def capture_baseline(self, protocol: EvaluationProtocol, baseline: Baseline) -> Baseline:
        self.protocol(protocol.protocol_id)
        if make_baseline(protocol,**{k:v for k,v in asdict(baseline).items() if k not in {"baseline_id","baseline_digest","schema_version","authority","protocol_id","protocol_digest","predecessor_generation"}})!=baseline: raise PostAdoptionEvaluationError("baseline_digest_mismatch")
        self._write("baselines",baseline.baseline_id,baseline); return baseline

    def protocol(self, identity: str) -> EvaluationProtocol:
        rows=[x for x in self._read("protocols") if x["protocol_id"]==identity]
        if len(rows)!=1: raise PostAdoptionEvaluationError("protocol_not_found")
        row=dict(rows[0]); row["measurements"]=tuple(MeasurementDefinition(**x) for x in row["measurements"]); return EvaluationProtocol(**row)

    def baseline(self, protocol_id: str) -> Baseline:
        rows=[x for x in self._read("baselines") if x["protocol_id"]==protocol_id]
        if len(rows)!=1: raise PostAdoptionEvaluationError("baseline_not_found")
        return Baseline(**rows[0])

    def observe(self, protocol: EvaluationProtocol, baseline: Baseline, qualification: SuccessorQualification, *, observations: Mapping[str,Any], source_records: Mapping[str,Mapping[str,str]], measurement_laws: Mapping[str,str], observed_at: str, collector_id: str) -> PostAdoptionObservation:
        if self._read("evaluations") and any(x["protocol_id"]==protocol.protocol_id for x in self._read("evaluations")): raise PostAdoptionEvaluationError("completed_evaluation_replay_forbidden")
        if (qualification.successor_generation!=protocol.expected_successor_generation or qualification.successor_commit!=protocol.landed_commit or qualification.successor_tree!=protocol.landed_tree or qualification.readiness_status!="resident_adoption_completed"):
            raise PostAdoptionEvaluationError("successor_not_exactly_qualified")
        if not all(str(x).startswith("sha256:") for x in (qualification.generation_digest,qualification.continuity_receipt_digest,qualification.adoption_receipt_digest,qualification.launch_provenance_digest,qualification.readiness_receipt_digest)): raise PostAdoptionEvaluationError("successor_evidence_digest_invalid")
        if not (protocol.created_at < baseline.observed_at < qualification.adoption_completed_at < observed_at): raise PostAdoptionEvaluationError("post_adoption_evaluation_not_preregistered")
        expected={m.observable_id:m.measurement_law for m in protocol.measurements}
        if dict(measurement_laws)!=expected: raise PostAdoptionEvaluationError("post_measurement_law_mismatch")
        raw=PostAdoptionObservation("","",protocol.protocol_id,protocol.protocol_digest,baseline.baseline_digest,
            protocol.predecessor_generation,qualification.successor_generation,baseline.source_revision,
            qualification.successor_commit,qualification.successor_tree,qualification.continuity_receipt_digest,
            qualification.adoption_receipt_digest,qualification.launch_provenance_digest,qualification.readiness_receipt_digest,
            dict(observations),dict(source_records),dict(measurement_laws),observed_at,collector_id,dict(FALSE_AUTHORITY))
        oid,odg=_identity("post-adoption-observation",raw.payload()); value=replace(raw,observation_id=oid,observation_digest=odg)
        self._write("observations",oid,value); return value

    def evaluate(self, protocol: EvaluationProtocol, baseline: Baseline, observation: PostAdoptionObservation, *, evaluated_at: str) -> Evaluation:
        if evaluated_at<=observation.observed_at: raise PostAdoptionEvaluationError("evaluation_not_after_observation")
        missing=[]; comparisons=[]
        for item in protocol.measurements:
            before=baseline.observations.get(item.observable_id); after=observation.observations.get(item.observable_id)
            if item.required and item.observable_id not in observation.observations: missing.append(item.observable_id); result="unmeasurable"
            else: result=_compare(item,before,after)
            comparisons.append({"observable_id":item.observable_id,"expected_value":item.expected_value,"predecessor_value":before,"successor_value":after,"comparator":item.comparator,"measurement_law":item.measurement_law,"protected_invariant":item.protected_invariant,"result":result,"source_record":observation.source_records.get(item.observable_id)})
        outcomes={x["result"] for x in comparisons}; protected_regression=any(x["protected_invariant"] and x["result"]=="regression_observed" for x in comparisons)
        if missing: result="insufficient_evidence"
        elif protected_regression: result="new_regression_observed" if outcomes<={"expected_change_observed","regression_observed"} else "mixed_outcome"
        elif outcomes=={"expected_change_observed"}: result="target_expectation_satisfied"
        elif outcomes=={"unchanged"}: result="no_detectable_change"
        elif outcomes<={"expected_change_absent","unchanged"}: result="target_expectation_contradicted"
        elif "unmeasurable" in outcomes: result="measurement_failed"
        else: result="mixed_outcome"
        lineage=(protocol.protocol_digest,baseline.baseline_digest,observation.continuity_receipt_digest,
            observation.adoption_receipt_digest,observation.readiness_receipt_digest,observation.observation_digest)
        raw=Evaluation("","",protocol.protocol_id,protocol.protocol_digest,protocol.maintenance_task_id,
            baseline.baseline_digest,observation.observation_digest,protocol.predecessor_generation,
            observation.successor_generation,baseline.source_revision,observation.successor_revision,tuple(comparisons),
            tuple(sorted(missing)),tuple(sorted(x["observable_id"] for x in comparisons if x["result"] in {"expected_change_absent","regression_observed"})),result,
            "controlled_before_after_correlation_not_experimental_causation",evaluated_at,lineage,
            protocol.validation_result_digest,dict(FALSE_AUTHORITY))
        eid,edg=_identity("post-adoption-evaluation",raw.payload()); value=replace(raw,evaluation_id=eid,evaluation_digest=edg)
        self._write("evaluations",eid,value)
        signal=improvement_signal_record(value)
        if signal: self._write("signals",eid,{**signal,"signal_handoff_only":True,"repository_mutation_performed":False})
        return value

    def recommend_rollback(self, evaluation: Evaluation, *, rationale: str, urgency: str) -> RollbackRecommendation:
        if evaluation.result not in {"new_regression_observed","mixed_outcome"}: raise PostAdoptionEvaluationError("rollback_recommendation_not_warranted")
        body={"evaluation_id":evaluation.evaluation_id,"current_generation":evaluation.successor_generation,"predecessor_generation":evaluation.predecessor_generation,"predecessor_revision":evaluation.predecessor_revision,"rationale":rationale,"urgency":urgency,"operator_decision_required":True,"executes_rollback":False,"authority":dict(FALSE_AUTHORITY),"schema_version":ROLLBACK_SCHEMA}
        rid,rdg=_identity("rollback-recommendation",body); value=RollbackRecommendation(rid,rdg,evaluation.evaluation_id,
            evaluation.successor_generation,evaluation.predecessor_generation,evaluation.predecessor_revision,
            rationale,urgency,True,False,dict(FALSE_AUTHORITY))
        self._write("recommendations",rid,value); return value

    def verify(self) -> Mapping[str,int]:
        protocols={}
        for raw in self._read("protocols"):
            value=dict(raw); value["measurements"]=tuple(value["measurements"]); rebuilt=make_protocol(**{k:v for k,v in value.items() if k not in {"protocol_id","protocol_digest","schema_version","authority"}})
            if rebuilt.protocol_digest!=value["protocol_digest"]: raise PostAdoptionEvaluationError("protocol_digest_mismatch")
            protocols[value["protocol_id"]]=value
        baselines={x["baseline_digest"]:x for x in self._read("baselines")}; observations={x["observation_digest"]:x for x in self._read("observations")}
        for raw in self._read("evaluations"):
            if raw["protocol_id"] not in protocols or raw["baseline_digest"] not in baselines or raw["observation_digest"] not in observations or raw["result"] not in RESULTS or digest({k:v for k,v in raw.items() if k not in {"evaluation_id","evaluation_digest"}})!=raw["evaluation_digest"]: raise PostAdoptionEvaluationError("evaluation_history_corrupt")
            _false(raw["authority"])
        return {"protocols":len(protocols),"baselines":len(baselines),"observations":len(observations),"evaluations":len(self._read("evaluations")),"signals":len(self._read("signals")),"recommendations":len(self._read("recommendations"))}


__all__=["MaintenancePostAdoptionEvaluationOwner","MeasurementDefinition","EvaluationProtocol","Baseline","SuccessorQualification","PostAdoptionObservation","Evaluation","RollbackRecommendation","make_protocol","make_baseline","improvement_signal_record","post_adoption_epistemic_binding","PostAdoptionEvaluationError","FALSE_AUTHORITY","COMPARATORS","RESULTS"]
