# mypy: ignore-errors
# mypy: disable-error-code="no-untyped-call,no-any-return"
"""Reviewed Genesis candidate adoption custody.

This module seals one proposal-ready Genesis evaluation into a data-only review
packet, binds an explicit operator decision, preflights separate control-plane
admissions, and executes only the exact reviewed candidate into an injectable
runtime-state root. It never drafts candidates, invokes models, runs Git, or
mutates repository source.
"""
from __future__ import annotations

import json, hashlib, os, tempfile
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence, Callable

from sentientos.control_plane_kernel import AuthorityClass, ControlActionRequest, LifecyclePhase, AdmissionOutcome, get_control_plane_kernel
from sentientos.world_state_board import WorldStateSourceKind

CANDIDATE_SCHEMA_VERSION="reviewed_genesis_candidate.v1"
PACKET_SCHEMA_VERSION="genesis_candidate_review_packet.v1"
DECISION_SCHEMA_VERSION="genesis_candidate_review_decision.v1"
PLAN_SCHEMA_VERSION="genesis_reviewed_adoption_plan.v1"
RECEIPT_SCHEMA_VERSION="genesis_reviewed_adoption_receipt.v1"
ROLLBACK_SCHEMA_VERSION="genesis_reviewed_adoption_rollback_receipt.v1"
VALID_DISPOSITIONS={"approve","reject","defer"}

if TYPE_CHECKING:
    from sentientos.genesis_forge import GenesisCandidateEvaluation

class GenesisReviewedAdoptionError(RuntimeError): pass
class GenesisReviewedAdoptionValidationError(GenesisReviewedAdoptionError): pass
class GenesisReviewedAdoptionConflict(GenesisReviewedAdoptionError): pass

@dataclass(frozen=True)
class GenesisReviewedAdoptionValidationResult:
    valid: bool
    findings: tuple[str,...]=()


def canonicalize(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return canonicalize(asdict(value))
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for k,v in sorted(value.items(), key=lambda i: str(i[0])):
            if callable(v):
                raise GenesisReviewedAdoptionValidationError("callable_content_rejected")
            out[str(k)] = canonicalize(v)
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        return [canonicalize(v) for v in value]
    if callable(value):
        raise GenesisReviewedAdoptionValidationError("callable_content_rejected")
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, (str,int,float,bool)) or value is None:
        return value
    raise GenesisReviewedAdoptionValidationError(f"unsupported_content:{type(value).__name__}")

def canonical_json(value: Any) -> str:
    return json.dumps(canonicalize(value), sort_keys=True, separators=(",",":"), ensure_ascii=False)

def digest_payload(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()

def _id(prefix: str, value: Any) -> str: return f"{prefix}-{digest_payload(value)[:24]}"
def _utc() -> str: return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data=(canonical_json(payload)+"\n").encode()
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(path.parent)) as h:
        h.write(data); tmp=Path(h.name)
    os.replace(tmp, path)

def safe_under(root: Path, *parts: str) -> Path:
    base=root.resolve(); path=(base.joinpath(*parts)).resolve()
    if base != path and base not in path.parents: raise GenesisReviewedAdoptionValidationError("path_escape_rejected")
    return path

@dataclass(frozen=True)
class ReviewedGenesisCandidate:
    schema_version: str
    candidate_id: str
    candidate_digest: str
    proposal_id: str
    spec_id: str
    normalized_need: Mapping[str, Any]
    capability: str
    source: str
    blueprint_name: str
    objective: str
    directives: tuple[str,...]
    testing_requirements: tuple[str,...]
    normalized_proposed_spec: Mapping[str, Any]
    original_spec_digest: str
    deltas: Mapping[str, Any]
    candidate_origin: str
    signal_batch_id: str
    signal_batch_digest: str
    evaluation_id: str
    evaluation_digest: str
    selected_router_candidate_id: str
    router_scorecard_digest: str
    stage_a_evidence_digest: str
    stage_b_evidence_digest: str
    sandbox_report_digest: str
    proof_budget_decision_digest: str
    advice_packet_id: str | None = None
    advice_packet_digest: str | None = None
    advice_request_id: str | None = None
    invocation_receipt_id: str | None = None
    invocation_receipt_digest: str | None = None
    no_authority: bool = True
    no_effect: bool = True
    repository_mutation_performed: bool = False

    def to_dict(self)->dict[str,Any]: return canonicalize(asdict(self))

@dataclass(frozen=True)
class GenesisCandidateReviewPacket:
    schema_version: str
    review_packet_id: str
    review_packet_digest: str
    candidate: ReviewedGenesisCandidate
    evaluation_digest: str
    router_scorecard_digest: str
    stage_a_evidence_digest: str
    stage_b_evidence_digest: str
    sandbox_report_digest: str
    proof_budget_decision_digest: str
    signal_batch_id: str
    signal_batch_digest: str
    custody: Mapping[str, Any]
    max_review_lifetime_seconds: int
    expires_at: str | None
    proposal_ready_for_review: bool = True
    lineage_integrated: bool = False
    adoption_performed: bool = False
    repository_mutation_performed: bool = False
    review_packet_grants_admission: bool = False
    review_packet_grants_execution: bool = False
    def to_dict(self)->dict[str,Any]: return canonicalize(asdict(self))

@dataclass(frozen=True)
class GenesisCandidateReviewDecision:
    schema_version: str
    decision_id: str
    decision_digest: str
    review_packet_id: str
    review_packet_digest: str
    candidate_id: str
    candidate_digest: str
    disposition: str
    reviewer: str
    reviewer_role: str
    reason_codes: tuple[str,...]
    note: str = ""
    custody_time: str = ""
    expires_at: str | None = None
    decision_grants_admission: bool = False
    decision_grants_execution: bool = False
    decision_performs_adoption: bool = False
    repository_mutation_performed: bool = False
    def to_dict(self)->dict[str,Any]: return canonicalize(asdict(self))

@dataclass(frozen=True)
class GenesisReviewedAdoptionPlan:
    schema_version: str
    plan_id: str
    plan_digest: str
    review_packet_id: str
    review_packet_digest: str
    decision_id: str
    decision_digest: str
    candidate_id: str
    candidate_digest: str
    attempt_id: str
    idempotency_key: str
    target_labels: Mapping[str,str]
    source_state_digest: str
    expected_prior_state_digest: str | None
    lineage_mutation_action: str
    adoption_mutation_action: str
    rollback_strategy: str
    staleness_policy: str
    audit_trust_posture: str
    repository_source_mutation: bool = False
    def to_dict(self)->dict[str,Any]: return canonicalize(asdict(self))

@dataclass(frozen=True)
class GenesisReviewedAdoptionReceipt:
    schema_version: str
    receipt_id: str
    receipt_digest: str
    attempt_id: str
    idempotency_key: str
    review_packet_id: str
    review_packet_digest: str
    decision_id: str
    decision_digest: str
    candidate_id: str
    candidate_digest: str
    plan_id: str
    plan_digest: str
    lineage_admission: Mapping[str,Any]
    adoption_admission: Mapping[str,Any]
    mutation_action_ids: tuple[str,str]
    lineage_result_digest: str
    adoption_result_digest: str
    target_state_digest: str
    status: str
    effect_evidence: Mapping[str,Any]
    repository_source_mutation: bool=False
    model_invocation: bool=False
    reevaluation: bool=False
    redrafting: bool=False
    def to_dict(self)->dict[str,Any]: return canonicalize(asdict(self))

@dataclass(frozen=True)
class GenesisReviewedAdoptionRollbackReceipt:
    schema_version: str
    rollback_id: str
    rollback_digest: str
    attempt_id: str
    candidate_id: str
    candidate_digest: str
    plan_id: str
    plan_digest: str
    status: str
    removed_paths: tuple[str,...]
    preserved_paths: tuple[str,...]
    reason: str
    append_only_audit_retained: bool=True
    def to_dict(self)->dict[str,Any]: return canonicalize(asdict(self))

def _semantic_candidate_payload(evaluation: "GenesisCandidateEvaluation", signal_batch: Mapping[str,Any], advice_packet: Mapping[str,Any]|None) -> dict[str,Any]:
    p=evaluation.proposal; need={"capability":p.need.capability,"description":p.need.description,"source":p.need.source}
    router=canonicalize(evaluation.router_scorecard); sandbox={"passed":evaluation.sandbox_report.passed,"results":evaluation.sandbox_report.results,"failures":evaluation.sandbox_report.failures}
    return {"schema_version":CANDIDATE_SCHEMA_VERSION,"proposal_id":p.proposal_id,"spec_id":p.spec_id,"normalized_need":need,"capability":p.need.capability,"source":p.need.source,"blueprint_name":p.blueprint.name,"objective":p.blueprint.objective,"directives":list(p.blueprint.directives),"testing_requirements":list(p.blueprint.testing_requirements),"normalized_proposed_spec":canonicalize(p.proposed_spec),"original_spec_digest":digest_payload(p.original_spec),"deltas":canonicalize(p.deltas),"candidate_origin":"genesis_candidate_evaluation","signal_batch_id":str(signal_batch.get("batch_id","signal-batch")),"signal_batch_digest":str(signal_batch.get("batch_digest") or digest_payload(signal_batch)),"evaluation_digest":digest_payload({"proposal":p.to_dict(),"router_scorecard":router,"sandbox_report":sandbox,"proof_budget_decision":evaluation.proof_budget_decision}),"selected_router_candidate_id":str(router.get("selected_candidate_id") or router.get("router_telemetry",{}).get("selected_candidate_id") or p.proposal_id),"router_scorecard_digest":digest_payload(router),"stage_a_evidence_digest":digest_payload(router.get("stage_a",[])),"stage_b_evidence_digest":digest_payload(router.get("stage_b",[])),"sandbox_report_digest":digest_payload(sandbox),"proof_budget_decision_digest":digest_payload(evaluation.proof_budget_decision),"advice_packet_id":(advice_packet or {}).get("packet_id"),"advice_packet_digest":(advice_packet or {}).get("packet_digest"),"advice_request_id":(advice_packet or {}).get("request_id") or router.get("advice",{}).get("request_id") if isinstance(router.get("advice"),Mapping) else None,"invocation_receipt_id":(advice_packet or {}).get("invocation_receipt_id"),"invocation_receipt_digest":(advice_packet or {}).get("invocation_receipt_digest")}

def reviewed_candidate_from_evaluation(evaluation: "GenesisCandidateEvaluation", *, signal_batch: Mapping[str,Any], advice_packet: Mapping[str,Any]|None=None) -> ReviewedGenesisCandidate:
    payload=_semantic_candidate_payload(evaluation, signal_batch, advice_packet); payload["evaluation_id"]=_id("genesis-evaluation", payload["evaluation_digest"])
    payload.update({"no_authority": True, "no_effect": True, "repository_mutation_performed": False})
    cid=_id("reviewed-genesis-candidate", payload); payload["candidate_id"]=cid; payload["candidate_digest"]=digest_payload(payload)
    return ReviewedGenesisCandidate(**payload)

def build_review_packet(evaluation: "GenesisCandidateEvaluation", *, signal_batch: Mapping[str,Any], advice_packet: Mapping[str,Any]|None=None, created_by: str="genesis_forge", created_at: str|None=None, max_review_lifetime_seconds: int=86400, expires_at: str|None=None) -> GenesisCandidateReviewPacket:
    c=reviewed_candidate_from_evaluation(evaluation, signal_batch=signal_batch, advice_packet=advice_packet)
    if c.selected_router_candidate_id != c.proposal_id: raise GenesisReviewedAdoptionValidationError("selected_candidate_mismatch")
    payload={"schema_version":PACKET_SCHEMA_VERSION,"candidate":c.to_dict(),"evaluation_digest":c.evaluation_digest,"router_scorecard_digest":c.router_scorecard_digest,"stage_a_evidence_digest":c.stage_a_evidence_digest,"stage_b_evidence_digest":c.stage_b_evidence_digest,"sandbox_report_digest":c.sandbox_report_digest,"proof_budget_decision_digest":c.proof_budget_decision_digest,"signal_batch_id":c.signal_batch_id,"signal_batch_digest":c.signal_batch_digest,"custody":{"created_by":created_by,"created_at":created_at or _utc()},"max_review_lifetime_seconds":max_review_lifetime_seconds,"expires_at":expires_at,"proposal_ready_for_review":True,"lineage_integrated":False,"adoption_performed":False,"repository_mutation_performed":False,"review_packet_grants_admission":False,"review_packet_grants_execution":False}
    pid=_id("genesis-review-packet", payload); payload["review_packet_id"]=pid; payload["review_packet_digest"]=digest_payload(payload)
    return GenesisCandidateReviewPacket(candidate=c, **{k:v for k,v in payload.items() if k!="candidate"})

def validate_review_packet(packet: GenesisCandidateReviewPacket|Mapping[str,Any], *, now: str|None=None) -> GenesisReviewedAdoptionValidationResult:
    p=packet.to_dict() if hasattr(packet,"to_dict") else canonicalize(packet); findings=[]
    if p.get("schema_version")!=PACKET_SCHEMA_VERSION: findings.append("unknown_schema")
    c=p.get("candidate",{})
    if c.get("schema_version")!=CANDIDATE_SCHEMA_VERSION: findings.append("unknown_candidate_schema")
    for f in ("candidate_id","candidate_digest","proposal_id","spec_id","stage_a_evidence_digest","stage_b_evidence_digest","sandbox_report_digest","proof_budget_decision_digest","signal_batch_digest"):
        if not c.get(f): findings.append(f"missing_{f}")
    semantic={k:v for k,v in c.items() if k not in {"candidate_id","candidate_digest"}}
    if c.get("candidate_id") != _id("reviewed-genesis-candidate", semantic): findings.append("candidate_id_mismatch")
    semantic_with_id=dict(semantic); semantic_with_id["candidate_id"]=c.get("candidate_id")
    if c.get("candidate_digest") != digest_payload(semantic_with_id): findings.append("candidate_digest_mismatch")
    for key in ("evaluation_digest","router_scorecard_digest","stage_a_evidence_digest","stage_b_evidence_digest","sandbox_report_digest","proof_budget_decision_digest","signal_batch_id","signal_batch_digest"):
        if p.get(key)!=c.get(key): findings.append(f"{key}_mismatch")
    if not p.get("proposal_ready_for_review"): findings.append("not_ready_for_review")
    for k in ("lineage_integrated","adoption_performed","repository_mutation_performed","review_packet_grants_admission","review_packet_grants_execution"):
        if p.get(k): findings.append(f"forbidden_{k}")
    base={k:v for k,v in p.items() if k not in {"review_packet_id","review_packet_digest"}}
    if p.get("review_packet_id") != _id("genesis-review-packet", base): findings.append("review_packet_id_mismatch")
    base_with_id=dict(base); base_with_id["review_packet_id"]=p.get("review_packet_id")
    if p.get("review_packet_digest") != digest_payload(base_with_id): findings.append("review_packet_digest_mismatch")
    if p.get("expires_at") and (now or _utc()) > str(p["expires_at"]): findings.append("expired_packet")
    return GenesisReviewedAdoptionValidationResult(not findings, tuple(findings))

def decide(packet: GenesisCandidateReviewPacket, *, disposition: str, reviewer: str, reviewer_role: str, reason_codes: Sequence[str], note: str="", custody_time: str|None=None, expires_at: str|None=None) -> GenesisCandidateReviewDecision:
    if disposition not in VALID_DISPOSITIONS: raise GenesisReviewedAdoptionValidationError("unsupported_disposition")
    if not reviewer or reviewer in {"*","wildcard","unknown"}: raise GenesisReviewedAdoptionValidationError("unknown_reviewer")
    if not packet.candidate.candidate_id or packet.candidate.candidate_id in {"*",""}: raise GenesisReviewedAdoptionValidationError("blank_candidate_reference")
    payload={"schema_version":DECISION_SCHEMA_VERSION,"review_packet_id":packet.review_packet_id,"review_packet_digest":packet.review_packet_digest,"candidate_id":packet.candidate.candidate_id,"candidate_digest":packet.candidate.candidate_digest,"disposition":disposition,"reviewer":reviewer,"reviewer_role":reviewer_role,"reason_codes":tuple(sorted(str(r) for r in reason_codes)),"note":note[:2048],"custody_time":custody_time or _utc(),"expires_at":expires_at,"decision_grants_admission":False,"decision_grants_execution":False,"decision_performs_adoption":False,"repository_mutation_performed":False}
    did=_id("genesis-review-decision", payload); payload["decision_id"]=did; payload["decision_digest"]=digest_payload(payload)
    return GenesisCandidateReviewDecision(**payload)

def validate_decision(decision: GenesisCandidateReviewDecision|Mapping[str,Any], packet: GenesisCandidateReviewPacket|None=None, *, now: str|None=None)->GenesisReviewedAdoptionValidationResult:
    d=decision.to_dict() if hasattr(decision,"to_dict") else canonicalize(decision); findings=[]
    if d.get("schema_version")!=DECISION_SCHEMA_VERSION: findings.append("unknown_schema")
    if d.get("disposition") not in VALID_DISPOSITIONS: findings.append("unsupported_disposition")
    if not d.get("reviewer") or d.get("reviewer") in {"*","unknown","wildcard"}: findings.append("unknown_reviewer")
    if not d.get("candidate_id") or d.get("candidate_id")=="*": findings.append("blank_candidate_reference")
    for k in ("decision_grants_admission","decision_grants_execution","decision_performs_adoption","repository_mutation_performed"):
        if d.get(k): findings.append(f"forbidden_{k}")
    base={k:v for k,v in d.items() if k not in {"decision_id","decision_digest"}}
    if d.get("decision_id") != _id("genesis-review-decision", base): findings.append("decision_id_mismatch")
    base_id=dict(base); base_id["decision_id"]=d.get("decision_id")
    if d.get("decision_digest") != digest_payload(base_id): findings.append("decision_digest_mismatch")
    if packet and (d.get("review_packet_id")!=packet.review_packet_id or d.get("candidate_digest")!=packet.candidate.candidate_digest): findings.append("packet_or_candidate_mismatch")
    if d.get("expires_at") and (now or _utc()) > str(d["expires_at"]): findings.append("expired_decision")
    return GenesisReviewedAdoptionValidationResult(not findings, tuple(findings))

def build_plan(packet: GenesisCandidateReviewPacket, decision: GenesisCandidateReviewDecision, *, runtime_root: Path|str, attempt_id: str|None=None, audit_trust_posture: str="nominal") -> GenesisReviewedAdoptionPlan:
    if not validate_review_packet(packet).valid: raise GenesisReviewedAdoptionValidationError("invalid_packet")
    dv=validate_decision(decision, packet); 
    if not dv.valid: raise GenesisReviewedAdoptionValidationError(",".join(dv.findings))
    if decision.disposition != "approve": raise GenesisReviewedAdoptionValidationError(f"decision_{decision.disposition}_is_non_mutating")
    root=Path(runtime_root); labels={"lineage":"integration/lineage/lineage.jsonl","covenant":"integration/covenant/daemons","live":"integration/live","index":"integration/codex_index.json"}
    aid=attempt_id or _id("genesis-adoption-attempt", (packet.review_packet_digest, decision.decision_digest))
    payload={"schema_version":PLAN_SCHEMA_VERSION,"review_packet_id":packet.review_packet_id,"review_packet_digest":packet.review_packet_digest,"decision_id":decision.decision_id,"decision_digest":decision.decision_digest,"candidate_id":packet.candidate.candidate_id,"candidate_digest":packet.candidate.candidate_digest,"attempt_id":aid,"idempotency_key":_id("genesis-adoption-idempotency", (packet.candidate.candidate_digest, decision.decision_digest)),"target_labels":labels,"source_state_digest":digest_payload({"root": "external_runtime_root", "candidate": packet.candidate.candidate_digest}),"expected_prior_state_digest":None,"lineage_mutation_action":"lineage_integrate_exact_reviewed_candidate","adoption_mutation_action":"promote_exact_reviewed_candidate","rollback_strategy":"digest_matching_created_state_only","staleness_policy":"fail_closed_no_refresh","audit_trust_posture":audit_trust_posture,"repository_source_mutation":False}
    payload["plan_id"]=_id("genesis-adoption-plan", payload); payload["plan_digest"]=digest_payload(payload)
    return GenesisReviewedAdoptionPlan(**payload)

class GenesisReviewedAdoptionCoordinator:
    def __init__(self, runtime_root: Path|str, *, kernel_provider: Callable[[],Any]|None=None) -> None:
        self.runtime_root=Path(runtime_root); self.kernel_provider=kernel_provider or get_control_plane_kernel
    def _path(self,*p:str)->Path: return safe_under(self.runtime_root,*p)
    def _admit(self, plan: GenesisReviewedAdoptionPlan, packet: GenesisCandidateReviewPacket, decision: GenesisCandidateReviewDecision, authority: AuthorityClass, action: str) -> Mapping[str,Any]:
        corr=f"{plan.attempt_id}:{action}"
        req=ControlActionRequest(action_kind=action, authority_class=authority, actor="genesis_reviewed_adoption", target_subsystem=packet.candidate.spec_id, requested_phase=LifecyclePhase.MAINTENANCE, metadata={"correlation_id":corr,"attempt_id":plan.attempt_id,"review_packet_id":packet.review_packet_id,"review_packet_digest":packet.review_packet_digest,"decision_id":decision.decision_id,"decision_digest":decision.decision_digest,"candidate_id":packet.candidate.candidate_id,"candidate_digest":packet.candidate.candidate_digest,"plan_id":plan.plan_id,"plan_digest":plan.plan_digest,"require_admissible":True})
        dec=self.kernel_provider().admit(req); d=dec.to_dict(); d["common_attempt_id"]=plan.attempt_id; return d
    def execute(self, packet: GenesisCandidateReviewPacket, decision: GenesisCandidateReviewDecision, plan: GenesisReviewedAdoptionPlan, *, apply: bool=False) -> GenesisReviewedAdoptionReceipt|GenesisReviewedAdoptionRollbackReceipt:
        if not apply: raise GenesisReviewedAdoptionValidationError("explicit_apply_required")
        if decision.disposition != "approve": raise GenesisReviewedAdoptionValidationError(f"decision_{decision.disposition}_is_non_mutating")
        if not validate_review_packet(packet).valid or not validate_decision(decision, packet).valid: raise GenesisReviewedAdoptionValidationError("invalid_packet_or_decision")
        receipt_path=self._path("genesis_reviewed_adoption","receipts",f"{plan.idempotency_key}.json")
        if receipt_path.exists(): return receipt_from_dict(json.loads(receipt_path.read_text()))
        lineage=self._admit(plan,packet,decision,AuthorityClass.MANIFEST_OR_IDENTITY_MUTATION,"lineage_integrate")
        adoption=self._admit(plan,packet,decision,AuthorityClass.PROPOSAL_ADOPTION,"proposal_adopt")
        if lineage.get("outcome")!="allow" or adoption.get("outcome")!="allow":
            return self._receipt(packet,decision,plan,lineage,adoption,"denied",{}, {}, {}, write=False)
        created=[]
        try:
            c=packet.candidate; spec={"name":c.blueprint_name,"objective":c.objective,"directives":list(c.directives),"testing_requirements":list(c.testing_requirements),"lineage":c.normalized_proposed_spec.get("lineage",{}),"reviewed_candidate_digest":c.candidate_digest}
            spec_path=self._path("integration","covenant","daemons",f"{c.blueprint_name}.json")
            live_path=self._path("integration","live",f"{c.blueprint_name}.json")
            index_path=self._path("integration","codex_index.json"); lineage_log=self._path("integration","lineage","lineage.jsonl")
            for p in (spec_path, live_path):
                if p.exists(): raise GenesisReviewedAdoptionConflict("conflicting_preexisting_state")
            _write_atomic(spec_path,spec); created.append(spec_path)
            lineage_entry={"proposal_id":c.proposal_id,"spec_id":c.spec_id,"candidate_digest":c.candidate_digest,"admission":lineage,"typed_action_id":"lineage_integrate_exact_reviewed_candidate"}
            lineage_log.parent.mkdir(parents=True, exist_ok=True)
            with lineage_log.open("a",encoding="utf-8") as h: h.write(canonical_json(lineage_entry)+"\n")
            live={"name":c.blueprint_name,"objective":c.objective,"candidate_digest":c.candidate_digest,"lineage":lineage_entry,"admission":adoption}
            _write_atomic(live_path,live); created.append(live_path)
            idx=[]
            if index_path.exists(): idx=json.loads(index_path.read_text())
            if any(e.get("spec_id")==c.spec_id and e.get("candidate_digest")!=c.candidate_digest for e in idx): raise GenesisReviewedAdoptionConflict("same_proposal_different_candidate_conflict")
            if not any(e.get("candidate_digest")==c.candidate_digest for e in idx): idx.append({"spec_id":c.spec_id,"proposal_id":c.proposal_id,"candidate_digest":c.candidate_digest,"status":"adopted"})
            _write_atomic(index_path,{"entries":idx}); created.append(index_path)
            receipt=self._receipt(packet,decision,plan,lineage,adoption,"adopted",lineage_entry,live,{"paths":[str(p) for p in created]}, write=True)
            return receipt
        except Exception as exc:
            return self._rollback(packet, plan, created, str(exc))
    def _receipt(self, packet, decision, plan, lineage, adoption, status, lineage_result, adoption_result, evidence, *, write: bool):
        payload={"schema_version":RECEIPT_SCHEMA_VERSION,"attempt_id":plan.attempt_id,"idempotency_key":plan.idempotency_key,"review_packet_id":packet.review_packet_id,"review_packet_digest":packet.review_packet_digest,"decision_id":decision.decision_id,"decision_digest":decision.decision_digest,"candidate_id":packet.candidate.candidate_id,"candidate_digest":packet.candidate.candidate_digest,"plan_id":plan.plan_id,"plan_digest":plan.plan_digest,"lineage_admission":lineage,"adoption_admission":adoption,"mutation_action_ids":("lineage_integrate_exact_reviewed_candidate","promote_exact_reviewed_candidate"),"lineage_result_digest":digest_payload(lineage_result),"adoption_result_digest":digest_payload(adoption_result),"target_state_digest":digest_payload(evidence),"status":status,"effect_evidence":evidence,"repository_source_mutation":False,"model_invocation":False,"reevaluation":False,"redrafting":False}
        payload["receipt_id"]=_id("genesis-adoption-receipt", payload); payload["receipt_digest"]=digest_payload(payload); r=GenesisReviewedAdoptionReceipt(**payload)
        if write: _write_atomic(self._path("genesis_reviewed_adoption","receipts",f"{plan.idempotency_key}.json"), r.to_dict())
        return r
    def _rollback(self, packet, plan, created: Sequence[Path], reason: str):
        removed=[]; preserved=[]
        for p in reversed(created):
            try:
                if p.exists(): p.unlink(); removed.append(str(p))
            except OSError: preserved.append(str(p))
        status="rolled_back" if not preserved else "degraded_partial"
        payload={"schema_version":ROLLBACK_SCHEMA_VERSION,"attempt_id":plan.attempt_id,"candidate_id":packet.candidate.candidate_id,"candidate_digest":packet.candidate.candidate_digest,"plan_id":plan.plan_id,"plan_digest":plan.plan_digest,"status":status,"removed_paths":tuple(removed),"preserved_paths":tuple(preserved),"reason":reason,"append_only_audit_retained":True}
        payload["rollback_id"]=_id("genesis-adoption-rollback", payload); payload["rollback_digest"]=digest_payload(payload); rb=GenesisReviewedAdoptionRollbackReceipt(**payload)
        _write_atomic(self._path("genesis_reviewed_adoption","rollbacks",f"{plan.attempt_id}.json"), rb.to_dict()); return rb

def receipt_from_dict(d: Mapping[str,Any])->GenesisReviewedAdoptionReceipt: return GenesisReviewedAdoptionReceipt(**canonicalize(d))

def world_state_records_for(packet: GenesisCandidateReviewPacket|None=None, decision: GenesisCandidateReviewDecision|None=None, plan: GenesisReviewedAdoptionPlan|None=None, receipt: GenesisReviewedAdoptionReceipt|None=None, rollback: GenesisReviewedAdoptionRollbackReceipt|None=None) -> list[dict[str,Any]]:
    out=[]
    if packet: out.append({"source_kind":WorldStateSourceKind.GENESIS_CANDIDATE.value,"source_id":packet.review_packet_id,"schema_version":packet.schema_version,"digest":packet.review_packet_digest,"subject_id":packet.candidate.candidate_id,"subject_kind":"genesis_review_packet","stage":"review","disposition":"ready_for_review","payload":{"packet_digest":packet.review_packet_digest}})
    if decision: out.append({"source_kind":WorldStateSourceKind.GENESIS_CANDIDATE.value,"source_id":decision.decision_id,"schema_version":decision.schema_version,"digest":decision.decision_digest,"subject_id":decision.candidate_id,"subject_kind":"genesis_review_decision","stage":"review","disposition":decision.disposition,"payload":{"decision_digest":decision.decision_digest}})
    if plan: out.append({"source_kind":WorldStateSourceKind.GENESIS_CANDIDATE.value,"source_id":plan.plan_id,"schema_version":plan.schema_version,"digest":plan.plan_digest,"subject_id":plan.candidate_id,"subject_kind":"genesis_adoption_plan","stage":"admission","disposition":"eligible","payload":{"plan_digest":plan.plan_digest}})
    if receipt: 
        out.append({"source_kind":WorldStateSourceKind.GENESIS_CANDIDATE.value,"source_id":receipt.receipt_id+":attempt","schema_version":receipt.schema_version,"digest":receipt.receipt_digest,"subject_id":receipt.candidate_id,"subject_kind":"genesis_adoption_attempt","stage":"execution","disposition":receipt.status,"effect_claimed":receipt.status=="adopted","effect_proven":receipt.status=="adopted","payload":{"receipt_digest":receipt.receipt_digest}})
        if receipt.status=="adopted": out.append({"source_kind":WorldStateSourceKind.GENESIS_CANDIDATE.value,"source_id":receipt.receipt_id+":adoption","schema_version":receipt.schema_version,"digest":receipt.receipt_digest,"subject_id":receipt.candidate_id,"subject_kind":"genesis_completed_adoption","stage":"adoption","disposition":"adopted","effect_claimed":True,"effect_proven":True,"payload":{"receipt_digest":receipt.receipt_digest}})
    if rollback: out.append({"source_kind":WorldStateSourceKind.GENESIS_CANDIDATE.value,"source_id":rollback.rollback_id,"schema_version":rollback.schema_version,"digest":rollback.rollback_digest,"subject_id":rollback.candidate_id,"subject_kind":"genesis_adoption_rollback","stage":"rollback","disposition":rollback.status,"payload":{"rollback_digest":rollback.rollback_digest}})
    return out
