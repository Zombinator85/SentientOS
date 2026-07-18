# mypy: disable-error-code="no-any-return,no-untyped-def,no-untyped-call,var-annotated,union-attr"
"""Canonical custody runtime for metadata-only fulfillment authorization consumption."""
from __future__ import annotations

import hashlib, json, os
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Mapping, Sequence

from sentientos.control_plane_kernel import AuthorityClass, ControlActionDecision, ControlActionRequest, ControlPlaneKernel, LifecyclePhase, get_control_plane_kernel
from sentientos.fulfillment_authorization import build_fulfillment_authorization_request, verify_grant_consumption_for_fulfillment, assess_fulfillment_scope_match, build_fulfillment_authorization_consumption_receipt, build_fulfillment_authorization_denial_receipt
from sentientos.local_authorization_grant import local_authorization_grant_digest, local_authorization_grant_verification_digest, local_authorization_grant_ledger_digest, local_authorization_grant_expiry_evaluation_digest, local_authorization_grant_revocation_receipt_digest
from sentientos.world_state_board import WorldStateSourceKind, digest as world_digest

SCHEMA_VERSION="host_fulfillment_authorization_runtime.v1"
_ALLOWED_REASONS={"operator_requested_future_fulfillment","local_subsystem_requested_future_fulfillment","diagnostic_review","safety_review"}
_LABEL_CHARS=set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:-.")
NO_EFFECT={"fulfillment_granted":False,"executor_authorized":False,"privileged_effect_admission_granted":False,"effect_performed":False,"host_mutation_performed":False}
_LOCK=Lock()

def _canon(o:Any)->str: return json.dumps(o, sort_keys=True, separators=(",",":"), default=lambda x: asdict(x) if hasattr(x,"__dataclass_fields__") else str(x))
def _dict(o:Any)->dict[str,Any]: return json.loads(_canon(o.to_dict() if hasattr(o,"to_dict") else o))
def _digest_payload(p:Mapping[str,Any])->str:
    q=dict(p); q["digest"]=""; return "sha256:"+hashlib.sha256(_canon(q).encode()).hexdigest()
def _id(prefix:str,p:Any)->str: return prefix+hashlib.sha256(_canon(p).encode()).hexdigest()[:24]
def _t(xs:Sequence[str]|None)->tuple[str,...]: return tuple(sorted(str(x) for x in (xs or ())))
def _parse(s:str)->datetime:
    dt=datetime.fromisoformat(str(s).replace("Z","+00:00"))
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
def _bound(labels:Sequence[str], prefix:str)->datetime|None:
    vals=[str(x).removeprefix(prefix) for x in labels if str(x).startswith(prefix)]
    return _parse(vals[0]) if vals else None
def _expiry_time(label:str)->datetime|None:
    return _parse(str(label).removeprefix("expires:")) if str(label).startswith("expires:") else None
def _same_record(a:Any,b:Any)->bool: return _dict(a)==_dict(b)
def _valid_label(s:str)->bool:
    return bool(s) and len(s)<=128 and s not in {"*","sample","example","test"} and all(c in _LABEL_CHARS for c in s) and not any(x in s for x in ("/","\\","$","`",";","|","&&","..","~","import","exec","eval","subprocess","class:","()"))

def _validate_labels(labels:Sequence[str], prefix:str)->list[str]: return [prefix+str(x) for x in labels if not _valid_label(str(x))]

@dataclass(frozen=True)
class HostFulfillmentAuthorizationSourceRef:
    schema_version:str; source_ref_id:str; digest:str; issue_receipt_id:str; issue_receipt_digest:str; grant_id:str; grant_digest:str; verification_id:str; verification_digest:str; ledger_id:str; ledger_digest:str; ledger_predecessor_digest:str; expiry_evaluation_id:str; expiry_evaluation_digest:str; revocation_receipt_ids:tuple[str,...]; revocation_receipt_digests:tuple[str,...]; runtime_root_ref:str="external_runtime_root"; metadata_only:bool=True; fulfillment_granted:bool=False; effect_performed:bool=False; host_mutation_performed:bool=False
    def to_dict(self)->dict[str,Any]: return asdict(self)

@dataclass(frozen=True)
class HostFulfillmentAuthorizationRequestEnvelope:
    schema_version:str; request_id:str; digest:str; requesting_actor:str; requesting_subsystem:str; reason_codes:tuple[str,...]; note:str; local_grant_id:str; local_grant_digest:str; issue_receipt_id:str; issue_receipt_digest:str; grant_verification_id:str; grant_verification_digest:str; local_authorization_ledger_id:str; local_authorization_ledger_digest:str; requested_fulfillment_domain:str; requested_backend_label:str; requested_scope_labels:tuple[str,...]; requested_target_labels:tuple[str,...]; requested_time:str; expected_not_before:str; expected_not_after:str; expected_expiry_posture:str; expected_revocation_posture:str; source_ref_id:str; source_ref_digest:str; idempotency_key:str; executor_contract_id:str|None=None; executor_contract_digest:str|None=None; effect_contract_id:str|None=None; effect_contract_digest:str|None=None; rollback_plan_id:str|None=None; rollback_plan_digest:str|None=None; postcondition_plan_id:str|None=None; postcondition_plan_digest:str|None=None; created_at:str="1970-01-01T00:00:00+00:00"; fulfillment_requested:bool=True; authorization_consumed_for_future_fulfillment:bool=False; fulfillment_granted:bool=False; executor_authorized:bool=False; privileged_effect_admission_granted:bool=False; effect_performed:bool=False; host_mutation_performed:bool=False
    def to_dict(self)->dict[str,Any]: return asdict(self)

@dataclass(frozen=True)
class HostFulfillmentAuthorizationConsumptionPlan:
    schema_version:str; plan_id:str; digest:str; request_id:str; request_digest:str; source_ref_id:str; source_ref_digest:str; local_grant_id:str; local_grant_digest:str; ledger_predecessor_digest:str; requested_fulfillment_domain:str; requested_backend_label:str; requested_scope_labels:tuple[str,...]; requested_target_labels:tuple[str,...]; requested_time:str; idempotency_key:str; attempt_id:str; correlation_id:str; admission_authority_class:str="fulfillment_authorization_consumption"; metadata_only:bool=True; authorizes_fulfillment:bool=False; effect_performed:bool=False; host_mutation_performed:bool=False
    def to_dict(self)->dict[str,Any]: return asdict(self)

@dataclass(frozen=True)
class HostFulfillmentAuthorizationValidationResult:
    ok:bool; status:str; findings:tuple[str,...]

@dataclass(frozen=True)
class HostFulfillmentAuthorizationRuntimeEvaluation:
    schema_version:str; evaluation_id:str; digest:str; request_id:str; request_digest:str; plan_id:str|None; plan_digest:str|None; status:str; findings:tuple[str,...]; admission_outcome:str|None; admission_ref:str|None; fulfillment_request:Mapping[str,Any]|None; grant_consumption_verification:Mapping[str,Any]|None; scope_match_assessment:Mapping[str,Any]|None; denial_receipt:Mapping[str,Any]|None; consumption_receipt:Mapping[str,Any]|None; missing_future_gates:tuple[str,...]; blocked_actions:tuple[str,...]; validation_time:str; authorization_consumed_for_future_fulfillment:bool=False; fulfillment_granted:bool=False; executor_authorized:bool=False; privileged_effect_admission_granted:bool=False; effect_performed:bool=False; host_mutation_performed:bool=False
    def to_dict(self)->dict[str,Any]: return asdict(self)

@dataclass(frozen=True)
class HostFulfillmentAuthorizationConsumptionLedgerEntry:
    schema_version:str; entry_id:str; digest:str; entry_status:str; request_id:str; request_digest:str; grant_id:str; grant_digest:str; plan_id:str; plan_digest:str; admission_ref:str|None; admission_outcome:str|None; receipt_id:str|None; receipt_digest:str|None; denial_receipt_id:str|None; denial_receipt_digest:str|None; requested_fulfillment_domain:str; requested_backend_label:str; requested_scope_labels:tuple[str,...]; requested_target_labels:tuple[str,...]; requested_time:str; idempotency_key:str; predecessor_ledger_digest:str; created_at:str; authorization_consumed_for_future_fulfillment:bool=False; fulfillment_granted:bool=False; executor_authorized:bool=False; privileged_effect_admission_granted:bool=False; effect_performed:bool=False; host_mutation_performed:bool=False
    def to_dict(self)->dict[str,Any]: return asdict(self)

@dataclass(frozen=True)
class HostFulfillmentAuthorizationConsumptionLedger:
    schema_version:str; ledger_id:str; digest:str; predecessor_ledger_id:str; predecessor_ledger_digest:str; entries:tuple[HostFulfillmentAuthorizationConsumptionLedgerEntry,...]; active_count:int; denied_count:int; expired_count:int; revoked_count:int; conflicted_count:int; historical_count:int; created_at:str; metadata_only:bool=True; fulfillment_granted:bool=False; executor_authorized:bool=False; privileged_effect_admission_granted:bool=False; effect_performed:bool=False; host_mutation_performed:bool=False
    def to_dict(self)->dict[str,Any]: return asdict(self)

@dataclass(frozen=True)
class HostFulfillmentAuthorizationRuntimeReceipt:
    schema_version:str; receipt_id:str; digest:str; evaluation_id:str; evaluation_digest:str; ledger_entry_id:str|None; ledger_entry_digest:str|None; consumption_ledger_id:str|None; consumption_ledger_digest:str|None; status:str; created_at:str; authorization_consumed_for_future_fulfillment:bool=False; fulfillment_granted:bool=False; executor_authorized:bool=False; privileged_effect_admission_granted:bool=False; effect_performed:bool=False; host_mutation_performed:bool=False
    def to_dict(self)->dict[str,Any]: return asdict(self)

def build_source_ref(issue_receipt:Any, grant:Any, verification:Any, ledger:Any, expiry_evaluation:Any, revocation_receipts:Sequence[Any]=(), *, predecessor_digest:str="genesis") -> HostFulfillmentAuthorizationSourceRef:
    ir,g,v,l,e=_dict(issue_receipt),_dict(grant),_dict(verification),_dict(ledger),_dict(expiry_evaluation)
    rev=tuple(_dict(r) for r in revocation_receipts)
    sem={"issue":ir.get("receipt_id"),"grant":g.get("grant_id"),"verification":v.get("verification_id"),"ledger":l.get("ledger_id"),"expiry":e.get("evaluation_id"),"revocations":tuple(r.get("receipt_id") for r in rev),"predecessor":predecessor_digest}
    obj=HostFulfillmentAuthorizationSourceRef(SCHEMA_VERSION,_id("hfasr_",sem),"",str(ir.get("receipt_id","")),str(ir.get("digest","")),str(g.get("grant_id","")),str(g.get("digest","")),str(v.get("verification_id","")),str(v.get("digest","")),str(l.get("ledger_id","")),str(l.get("digest","")),predecessor_digest,str(e.get("evaluation_id","")),str(e.get("digest","")),tuple(str(r.get("receipt_id","")) for r in rev),tuple(str(r.get("digest","")) for r in rev))
    return replace(obj,digest=_digest_payload(obj.to_dict()))

def build_request_envelope(*, requesting_actor:str, requesting_subsystem:str, reason_codes:Sequence[str], note:str="", source_ref:HostFulfillmentAuthorizationSourceRef, requested_fulfillment_domain:str, requested_backend_label:str, requested_scope_labels:Sequence[str], requested_target_labels:Sequence[str], requested_time:str, expected_not_before:str, expected_not_after:str, expected_expiry_posture:str="local_authorization_expiry_not_expired", expected_revocation_posture:str="not_revoked", idempotency_key:str|None=None, request_id:str|None=None, created_at:str="1970-01-01T00:00:00+00:00", **optional:Any) -> HostFulfillmentAuthorizationRequestEnvelope:
    sem={"actor":requesting_actor,"subsystem":requesting_subsystem,"reasons":_t(reason_codes),"note":note,"source":source_ref.digest,"domain":requested_fulfillment_domain,"backend":requested_backend_label,"scope":_t(requested_scope_labels),"targets":_t(requested_target_labels),"time":requested_time,"not_before":expected_not_before,"not_after":expected_not_after,"expiry":expected_expiry_posture,"revocation":expected_revocation_posture}
    rid=request_id or _id("hfarq_",sem); idem=idempotency_key or _id("hfaidem_",sem)
    obj=HostFulfillmentAuthorizationRequestEnvelope(SCHEMA_VERSION,rid,"",requesting_actor,requesting_subsystem,_t(reason_codes),note,source_ref.grant_id,source_ref.grant_digest,source_ref.issue_receipt_id,source_ref.issue_receipt_digest,source_ref.verification_id,source_ref.verification_digest,source_ref.ledger_id,source_ref.ledger_digest,requested_fulfillment_domain,requested_backend_label,_t(requested_scope_labels),_t(requested_target_labels),requested_time,expected_not_before,expected_not_after,expected_expiry_posture,expected_revocation_posture,source_ref.source_ref_id,source_ref.digest,idem,optional.get("executor_contract_id"),optional.get("executor_contract_digest"),optional.get("effect_contract_id"),optional.get("effect_contract_digest"),optional.get("rollback_plan_id"),optional.get("rollback_plan_digest"),optional.get("postcondition_plan_id"),optional.get("postcondition_plan_digest"),created_at)
    return replace(obj,digest=_digest_payload(obj.to_dict()))

def validate_request_envelope(env:HostFulfillmentAuthorizationRequestEnvelope|Mapping[str,Any])->HostFulfillmentAuthorizationValidationResult:
    p=_dict(env); f=[]
    if p.get("schema_version")!=SCHEMA_VERSION: f.append("unknown_schema")
    if p.get("digest")!=_digest_payload(p): f.append("digest_mismatch")
    for field in ("request_id","requesting_actor","requesting_subsystem","requested_backend_label"):
        if not _valid_label(str(p.get(field,""))): f.append(f"invalid_{field}")
    f += _validate_labels(p.get("requested_scope_labels",()),"invalid_scope_label:") + _validate_labels(p.get("requested_target_labels",()),"invalid_target_label:")
    if not set(p.get("reason_codes",())) <= _ALLOWED_REASONS: f.append("unbounded_reason_code")
    if len(str(p.get("note","")))>240 or any(x in str(p.get("note","")) for x in ("`","$",";","&&","|")): f.append("unsafe_note")
    if not p.get("fulfillment_requested") or p.get("authorization_consumed_for_future_fulfillment") or any(p.get(k) for k in NO_EFFECT): f.append("forbidden_authority_claim")
    try: _parse(str(p.get("requested_time"))); _parse(str(p.get("expected_not_before"))); _parse(str(p.get("expected_not_after")))
    except Exception: f.append("invalid_time")
    return HostFulfillmentAuthorizationValidationResult(not f,"valid" if not f else "malformed",tuple(f))

def build_consumption_plan(env:HostFulfillmentAuthorizationRequestEnvelope, source_ref:HostFulfillmentAuthorizationSourceRef, *, attempt_id:str|None=None, correlation_id:str|None=None)->HostFulfillmentAuthorizationConsumptionPlan:
    sem={"request":env.request_id,"request_digest":env.digest,"source":source_ref.digest,"idem":env.idempotency_key}
    obj=HostFulfillmentAuthorizationConsumptionPlan(SCHEMA_VERSION,_id("hfaplan_",sem),"",env.request_id,env.digest,source_ref.source_ref_id,source_ref.digest,env.local_grant_id,env.local_grant_digest,source_ref.ledger_predecessor_digest,env.requested_fulfillment_domain,env.requested_backend_label,env.requested_scope_labels,env.requested_target_labels,env.requested_time,env.idempotency_key,attempt_id or _id("hfaatt_",sem),correlation_id or _id("hfacorr_",sem))
    return replace(obj,digest=_digest_payload(obj.to_dict()))

class HostFulfillmentAuthorizationRuntimeCoordinator:
    def __init__(self, runtime_state_root:Path|str|None=None, *, kernel:ControlPlaneKernel|None=None, clock:Callable[[],datetime]|None=None):
        self.root=Path(runtime_state_root or os.environ.get("SENTIENTOS_RUNTIME_STATE_ROOT","/tmp/sentientos_runtime_state"))/"host_fulfillment_authorization"; self.kernel=kernel or get_control_plane_kernel(); self.clock=clock or (lambda: datetime.now(timezone.utc))
    def _path(self,*parts:str)->Path:
        p=(self.root.joinpath(*parts)).resolve(); root=self.root.resolve()
        if not str(p).startswith(str(root)): raise ValueError("path_traversal")
        return p
    def _write(self,path:Path,obj:Any)->None:
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and path.is_symlink(): raise ValueError("symlink_escape")
        tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(_canon(obj),encoding="utf-8"); tmp.replace(path)
    def _load_ledger(self)->HostFulfillmentAuthorizationConsumptionLedger:
        p=self._path("ledger.json")
        if not p.exists():
            base=HostFulfillmentAuthorizationConsumptionLedger(SCHEMA_VERSION,"hfa_ledger_genesis","","", "genesis",(),0,0,0,0,0,0,self.clock().isoformat())
            return replace(base,digest=_digest_payload(base.to_dict()))
        d=json.loads(p.read_text()); entries=tuple(HostFulfillmentAuthorizationConsumptionLedgerEntry(**e) for e in d.get("entries",()))
        return HostFulfillmentAuthorizationConsumptionLedger(**{**d,"entries":entries})
    def _admit(self, env:HostFulfillmentAuthorizationRequestEnvelope, src:HostFulfillmentAuthorizationSourceRef, plan:HostFulfillmentAuthorizationConsumptionPlan)->ControlActionDecision:
        return self.kernel.admit(ControlActionRequest("host_fulfillment_authorization_consumption",AuthorityClass.FULFILLMENT_AUTHORIZATION_CONSUMPTION,"operator_or_local_subsystem","host_fulfillment_authorization_runtime",LifecyclePhase.MAINTENANCE,{"request_id":env.request_id,"request_digest":env.digest,"issue_receipt_id":src.issue_receipt_id,"issue_receipt_digest":src.issue_receipt_digest,"grant_id":src.grant_id,"grant_digest":src.grant_digest,"grant_verification_id":src.verification_id,"grant_verification_digest":src.verification_digest,"ledger_id":src.ledger_id,"ledger_digest":src.ledger_digest,"consumption_plan_id":plan.plan_id,"consumption_plan_digest":plan.digest,"requested_domain":env.requested_fulfillment_domain,"requested_backend":env.requested_backend_label,"requested_scope":env.requested_scope_labels,"requested_targets":env.requested_target_labels,"requested_time":env.requested_time,"idempotency_key":env.idempotency_key,"attempt_id":plan.attempt_id,"correlation_id":plan.correlation_id,"metadata_only":True,"grants_fulfillment":False,"grants_privileged_effect_admission":False,"executes_backend":False,"performs_effect":False}))
    def evaluate(self, env:HostFulfillmentAuthorizationRequestEnvelope, src:HostFulfillmentAuthorizationSourceRef, issue_receipt:Any, grant:Any, verification:Any, ledger:Any, expiry_evaluation:Any, revocation_receipts:Sequence[Any]=(), *, apply:bool=False, admission:ControlActionDecision|None=None)->tuple[HostFulfillmentAuthorizationRuntimeEvaluation,HostFulfillmentAuthorizationRuntimeReceipt]:
        with _LOCK:
            current_time=self.clock(); now=current_time.isoformat(); findings=list(validate_request_envelope(env).findings); g,v,l,e,ir=_dict(grant),_dict(verification),_dict(ledger),_dict(expiry_evaluation),_dict(issue_receipt)
            revs=[_dict(r) for r in revocation_receipts]
            recomputed_src=build_source_ref(issue_receipt,grant,verification,ledger,expiry_evaluation,revocation_receipts,predecessor_digest=str(getattr(src,"ledger_predecessor_digest",_dict(src).get("ledger_predecessor_digest","genesis"))))
            supplied_src=_dict(src)
            if not _same_record(src,recomputed_src) or env.source_ref_id!=recomputed_src.source_ref_id or env.source_ref_digest!=recomputed_src.digest:
                findings.append("source_ref_mismatch")
            if recomputed_src.grant_id!=env.local_grant_id or recomputed_src.grant_digest!=env.local_grant_digest or supplied_src.get("grant_id")!=recomputed_src.grant_id or supplied_src.get("grant_digest")!=recomputed_src.grant_digest: findings.append("source_ref_grant_mismatch")
            if recomputed_src.issue_receipt_id!=env.issue_receipt_id or recomputed_src.issue_receipt_digest!=env.issue_receipt_digest or supplied_src.get("issue_receipt_id")!=recomputed_src.issue_receipt_id or supplied_src.get("issue_receipt_digest")!=recomputed_src.issue_receipt_digest: findings.append("source_ref_issue_receipt_mismatch")
            if recomputed_src.verification_id!=env.grant_verification_id or recomputed_src.verification_digest!=env.grant_verification_digest or supplied_src.get("verification_id")!=recomputed_src.verification_id or supplied_src.get("verification_digest")!=recomputed_src.verification_digest: findings.append("source_ref_verification_mismatch")
            if recomputed_src.ledger_id!=env.local_authorization_ledger_id or recomputed_src.ledger_digest!=env.local_authorization_ledger_digest or supplied_src.get("ledger_id")!=recomputed_src.ledger_id or supplied_src.get("ledger_digest")!=recomputed_src.ledger_digest or supplied_src.get("ledger_predecessor_digest")!=recomputed_src.ledger_predecessor_digest: findings.append("source_ref_ledger_mismatch")
            if supplied_src.get("expiry_evaluation_id")!=recomputed_src.expiry_evaluation_id or supplied_src.get("expiry_evaluation_digest")!=recomputed_src.expiry_evaluation_digest: findings.append("source_ref_expiry_mismatch")
            if tuple(supplied_src.get("revocation_receipt_digests",()))!=recomputed_src.revocation_receipt_digests: findings.append("source_ref_revocation_mismatch")
            src=recomputed_src
            if env.local_grant_digest!=local_authorization_grant_digest(g) or env.local_grant_digest!=g.get("digest"): findings.append("grant_digest_mismatch")
            if env.grant_verification_digest!=local_authorization_grant_verification_digest(v) or v.get("grant_id")!=env.local_grant_id: findings.append("verification_mismatch")
            if env.local_authorization_ledger_digest!=local_authorization_grant_ledger_digest(l): findings.append("ledger_mismatch")
            if ir.get("grant_id")!=env.local_grant_id or ir.get("grant_digest")!=env.local_grant_digest: findings.append("issue_receipt_mismatch")
            grants=l.get("grant_records",()) or []
            matches=[x for x in grants if isinstance(x,Mapping) and x.get("grant_id")==env.local_grant_id]
            if not matches: findings.append("ledger_missing_exact_grant")
            if len({local_authorization_grant_digest(x) for x in matches})>1: findings.append("duplicate_grant_id_different_bytes")
            if e.get("grant_id")!=env.local_grant_id or e.get("grant_digest", env.local_grant_digest)!=env.local_grant_digest or env.expected_expiry_posture!=e.get("expiry_status") or local_authorization_grant_expiry_evaluation_digest(e)!=e.get("digest"): findings.append("expiry_mismatch")
            if str(e.get("expiry_label","")) != str(g.get("expiry_label","")): findings.append("expiry_mismatch")
            if any(r.get("grant_id")!=env.local_grant_id or local_authorization_grant_revocation_receipt_digest(r)!=r.get("digest") for r in revs): findings.append("revocation_mismatch")
            try:
                rt, nb_env, na_env=_parse(env.requested_time), _parse(env.expected_not_before), _parse(env.expected_not_after)
                grant_nb=_bound(g.get("granted_time_bounds",()),"not_before:") or nb_env
                grant_na=_bound(g.get("granted_time_bounds",()),"not_after:") or na_env
                grant_exp=_expiry_time(str(g.get("expiry_label","")))
                eval_at=_parse(str(e.get("evaluated_at","")))
                if rt<nb_env or rt<grant_nb: findings.append("not_yet_valid_grant")
                if rt>na_env or rt>grant_na or (grant_exp is not None and rt>grant_exp): findings.append("expired_grant")
                if grant_exp is not None and current_time>grant_exp: findings.append("expired_grant")
                if eval_at>rt: findings.append("expiry_evaluation_after_requested_time_unsupported")
                if e.get("expiry_status")=="local_authorization_expiry_not_expired" and eval_at<rt: findings.append("stale_expiry_evidence")
                if e.get("expiry_status")=="local_authorization_expiry_not_expired" and eval_at<current_time: findings.append("stale_expiry_evidence")
                if rt < current_time-timedelta(minutes=5): findings.append("backdated_request_not_supported")
                if rt > current_time+timedelta(days=1): findings.append("future_time_beyond_bounded_window")
            except Exception: findings.append("invalid_time")
            if e.get("expiry_status")=="local_authorization_expiry_expired": findings.append("expired_grant")
            if any(r.get("revocation_status")=="local_authorization_revocation_recorded" for r in revs) or "revoked" in str(v.get("verification_status")): findings.append("revoked_grant")
            if not str(g.get("grant_status","")).startswith("local_authorization_grant_active"): findings.append("blocked_incomplete_or_contradicted_grant")
            if set(env.requested_scope_labels)-set(g.get("granted_scope_labels",())): findings.append("out_of_scope_request")
            if set(env.requested_target_labels)-set(ir.get("target_labels", env.requested_target_labels)): findings.append("target_expansion")
            if any(g.get(k) for k in ("fulfillment_granted","effect_performed","host_mutation_performed")): findings.append("source_claims_fulfillment_or_effect")
            plan=build_consumption_plan(env,src); adm=(admission or self._admit(env,src,plan)) if apply and not findings else None
            fr=build_fulfillment_authorization_request(g,v,requested_fulfillment_domain=env.requested_fulfillment_domain,requested_backend_class=env.requested_backend_label,requested_scope_labels=env.requested_scope_labels,requested_time_label=env.requested_time,request_id=env.request_id,created_at=env.created_at)
            gv=verify_grant_consumption_for_fulfillment(g,v,fr); sa=assess_fulfillment_scope_match(g,fr)
            allowed=bool(apply and not findings and adm and adm.allowed and adm.authority_class==AuthorityClass.FULFILLMENT_AUTHORIZATION_CONSUMPTION)
            if apply and not allowed and not findings: findings.append("metadata_consumption_admission_not_allowed")
            ledger=self._load_ledger(); conflict=None
            for ent in ledger.entries:
                if ent.idempotency_key==env.idempotency_key and ent.request_digest!=env.digest: conflict="idempotency_conflict"
                if ent.request_id==env.request_id and ent.request_digest!=env.digest: conflict="request_id_conflict"
                if ent.request_id==env.request_id and ent.grant_id!=env.local_grant_id: conflict="request_grant_conflict"
                if ent.request_id==env.request_id and (ent.requested_scope_labels!=env.requested_scope_labels or ent.requested_target_labels!=env.requested_target_labels or ent.requested_backend_label!=env.requested_backend_label or ent.requested_time!=env.requested_time): conflict="semantic_request_conflict"
                if ent.request_id==env.request_id and ent.request_digest==env.digest:
                    ev=self._evaluation(env,plan,"replayed",(),adm,fr,gv,sa,None,None,now)
                    rec=HostFulfillmentAuthorizationRuntimeReceipt(SCHEMA_VERSION,_id("hfarec_",(ev.digest,ent.digest)),"",ev.evaluation_id,ev.digest,ent.entry_id,ent.digest,ledger.ledger_id,ledger.digest,"replayed",now,ent.authorization_consumed_for_future_fulfillment)
                    return ev, replace(rec,digest=_digest_payload(rec.to_dict()))
            if conflict: findings.append(conflict)
            success=allowed and not findings and gv.consumption_status in {"grant_consumption_verified","grant_consumption_verified_with_conditions"} and sa.scope_match_status in {"fulfillment_scope_match","fulfillment_scope_match_with_conditions"}
            cr=build_fulfillment_authorization_consumption_receipt(fr,gv,sa,created_at=now) if success else None
            dr=None if success else build_fulfillment_authorization_denial_receipt(fr,gv,sa,created_at=now)
            status="consumption_recorded" if success else ("not_applied" if not apply and not findings else "denied")
            ev=self._evaluation(env,plan,status,findings,adm,fr,gv,sa,cr,dr,now)
            entry=None; newledger=ledger
            if success:
                entry0=HostFulfillmentAuthorizationConsumptionLedgerEntry(SCHEMA_VERSION,_id("hfaent_",(env.digest,cr.digest,ledger.digest)),"","consumption_recorded",env.request_id,env.digest,env.local_grant_id,env.local_grant_digest,plan.plan_id,plan.digest,adm.admission_decision_ref if adm else None,adm.outcome.value if adm else None,cr.receipt_id,cr.digest,None,None,env.requested_fulfillment_domain,env.requested_backend_label,env.requested_scope_labels,env.requested_target_labels,env.requested_time,env.idempotency_key,ledger.digest,now,True)
                entry=replace(entry0,digest=_digest_payload(entry0.to_dict()))
                ents=tuple(list(ledger.entries)+[entry]); new0=HostFulfillmentAuthorizationConsumptionLedger(SCHEMA_VERSION,_id("hfaledger_",[e.digest for e in ents]),"",ledger.ledger_id,ledger.digest,ents,sum(e.authorization_consumed_for_future_fulfillment for e in ents),sum(e.entry_status.startswith("denied") for e in ents),sum("expired" in e.entry_status for e in ents),sum("revoked" in e.entry_status for e in ents),sum("conflict" in e.entry_status for e in ents),len(ents),now)
                newledger=replace(new0,digest=_digest_payload(new0.to_dict()))
                self._persist(env,src,plan,adm,fr,gv,sa,cr,dr,entry,newledger,ev)
            rec0=HostFulfillmentAuthorizationRuntimeReceipt(SCHEMA_VERSION,_id("hfarec_",(ev.digest, entry.digest if entry else "denial")),"",ev.evaluation_id,ev.digest,entry.entry_id if entry else None,entry.digest if entry else None,newledger.ledger_id if entry else None,newledger.digest if entry else None,status,now,bool(entry))
            return ev, replace(rec0,digest=_digest_payload(rec0.to_dict()))
    def _evaluation(self,env,plan,status,findings,adm,fr,gv,sa,cr,dr,now):
        miss=("fulfillment_executor_contract_validation","privileged_effect_admission","fulfillment_specific_control_plane_admission","runtime_supervisor_live_observation","audit_receipt","immutable_trace","effect_receipt","completed_postcondition_check","rollback_receipt","panic_stop_posture","current_safety_gate_verification")
        blocked=tuple(sorted(set(getattr(fr,"blocked_actions",()))|set(getattr(gv,"blocked_actions",()))))
        ev0=HostFulfillmentAuthorizationRuntimeEvaluation(SCHEMA_VERSION,_id("hfaeval_",(env.digest,plan.digest,status,tuple(findings),adm.outcome.value if adm else None)),"",env.request_id,env.digest,plan.plan_id,plan.digest,status,tuple(sorted(findings)),adm.outcome.value if adm else None,adm.admission_decision_ref if adm else None,fr.to_dict(),gv.to_dict(),sa.to_dict(),dr.to_dict() if dr else None,cr.to_dict() if cr else None,miss,blocked,now,bool(cr and cr.authorization_consumed_for_future_fulfillment))
        return replace(ev0,digest=_digest_payload(ev0.to_dict()))
    def _persist(self,env,src,plan,adm,fr,gv,sa,cr,dr,entry,ledger,ev):
        docs={"requests/%s.json"%env.request_id:env.to_dict(),"source_refs/%s.json"%src.source_ref_id:src.to_dict(),"plans/%s.json"%plan.plan_id:plan.to_dict(),"admissions/%s.json"%plan.attempt_id:(adm.to_dict() if adm else {}),"fulfillment_requests/%s.json"%fr.request_id:fr.to_dict(),"verifications/%s.json"%gv.verification_id:gv.to_dict(),"scope_assessments/%s.json"%sa.assessment_id:sa.to_dict(),"receipts/%s.json"%(cr.receipt_id if cr else dr.receipt_id):(cr.to_dict() if cr else dr.to_dict()),"entries/%s.json"%entry.entry_id:entry.to_dict(),"ledger.json":ledger.to_dict(),"validation/%s.json"%ev.evaluation_id:ev.to_dict(),"summary.json":summary_for_evaluation(ev),"README.md":render_markdown(ev,ledger),"latest.json":{"request_id":env.request_id,"request_digest":env.digest,"evaluation_id":ev.evaluation_id,"ledger_id":ledger.ledger_id,"ledger_digest":ledger.digest}}
        for rel,obj in docs.items(): self._write(self._path(rel),obj)

def summary_for_evaluation(ev:HostFulfillmentAuthorizationRuntimeEvaluation|Mapping[str,Any])->dict[str,Any]:
    p=_dict(ev); return {"status":p.get("status"),"request_id":p.get("request_id"),"authorization_consumed_for_future_fulfillment":p.get("authorization_consumed_for_future_fulfillment",False),"findings":p.get("findings",()),"missing_future_gates":p.get("missing_future_gates",()),**NO_EFFECT}

def render_markdown(ev:HostFulfillmentAuthorizationRuntimeEvaluation|Mapping[str,Any], ledger:HostFulfillmentAuthorizationConsumptionLedger|Mapping[str,Any]|None=None)->str:
    s=summary_for_evaluation(ev); return "# Host Fulfillment Authorization Consumption Custody\n\n"+"\n".join(f"- {k}: {v}" for k,v in sorted(s.items()))+"\n"

def world_state_records(*objects:Any, observed_at:str="1970-01-01T00:00:00+00:00")->list[dict[str,Any]]:
    out=[]
    for obj in objects:
        if obj is None: continue
        p=_dict(obj); name=obj.__class__.__name__ if hasattr(obj,"__class__") else str(p.get("schema_version","record"))
        kind={"HostFulfillmentAuthorizationRequestEnvelope":"host_fulfillment_authorization_request","HostFulfillmentAuthorizationConsumptionPlan":"host_fulfillment_authorization_plan","HostFulfillmentAuthorizationRuntimeEvaluation":"host_fulfillment_authorization_evaluation","HostFulfillmentAuthorizationRuntimeReceipt":"host_fulfillment_authorization_runtime_receipt","HostFulfillmentAuthorizationConsumptionLedgerEntry":"host_fulfillment_authorization_ledger_entry","HostFulfillmentAuthorizationConsumptionLedger":"host_fulfillment_authorization_ledger","HostFulfillmentAuthorizationSourceRef":"host_fulfillment_authorization_source_ref"}.get(name,"host_fulfillment_authorization_record")
        stage="proposal" if "request" in kind else "review" if any(x in kind for x in ("plan","source","evaluation")) else "admission" if "receipt" in kind else "observation"
        disposition=str(p.get("status") or p.get("entry_status") or "recorded")
        sid=str(p.get("request_id") or p.get("plan_id") or p.get("evaluation_id") or p.get("receipt_id") or p.get("entry_id") or p.get("ledger_id") or p.get("source_ref_id"))
        payload={**p,"authorization_consumed_for_future_fulfillment":bool(p.get("authorization_consumed_for_future_fulfillment",False)),"effect_claimed":False,"effect_proven":False,**NO_EFFECT}
        out.append({"source_kind":WorldStateSourceKind.FULFILLMENT.value,"schema_version":SCHEMA_VERSION,"observed_at":observed_at,"required":False,"evidence_strength":"recorded","effect_claimed":False,"effect_proven":False,"source_id":f"hfa:{sid}:{kind}","subject_id":sid,"subject_kind":kind,"stage":stage,"disposition":disposition,"payload":payload,"digest":world_digest(payload)})
    return out

def dashboard_projection(records:Sequence[Mapping[str,Any]])->dict[str,Any]:
    counts={k:0 for k in ("request","consumption_recorded","denied","blocked","expired","revoked","out_of_scope","incomplete","contradicted","stale","conflicted")}; domains=set(); backends=set(); scopes=set(); targets=set(); gates=set(); blocks=set(); latest=[]
    for r in records:
        p=r.get("payload",{}) if isinstance(r.get("payload"),Mapping) else {}; latest.append(str(r.get("subject_id","")))
        k=str(r.get("subject_kind","")); st=str(p.get("status") or p.get("entry_status") or r.get("disposition",""))
        if "request" in k: counts["request"]+=1
        if p.get("authorization_consumed_for_future_fulfillment"): counts["consumption_recorded"]+=1
        for name in list(counts):
            if name in st or any(name in str(f) for f in p.get("findings",())): counts[name]+= int(name not in {"request","consumption_recorded"})
        domains.add(str(p.get("requested_fulfillment_domain",""))); backends.add(str(p.get("requested_backend_label") or p.get("requested_backend_class") or "")); scopes.update(map(str,p.get("requested_scope_labels",()) or ())); targets.update(map(str,p.get("requested_target_labels",()) or ())); gates.update(map(str,p.get("missing_future_gates",()) or ())); blocks.update(map(str,p.get("blocked_actions",()) or ()))
    return {"status":"recorded" if records else "unavailable","request_count":counts["request"],"consumption_recorded_count":counts["consumption_recorded"],"denied_count":counts["denied"],"blocked_count":counts["blocked"],"expired_count":counts["expired"],"revoked_count":counts["revoked"],"out_of_scope_count":counts["out_of_scope"],"incomplete_count":counts["incomplete"],"contradicted_count":counts["contradicted"],"stale_count":counts["stale"],"conflicted_count":counts["conflicted"],"domains":sorted(x for x in domains if x),"backend_posture":sorted(x for x in backends if x),"requested_scope_summaries":sorted(scopes),"requested_target_summaries":sorted(targets),"missing_future_gates":sorted(gates),"blocked_actions":sorted(blocks),"latest_ids":[x for x in latest[-20:] if x],"read_only":True,"authorization_consumption_metadata_only":True,"fulfillment_granted":False,"executor_authorized":False,"execution_triggered":False,"effect_performed":False,"host_mutation_performed":False}
