"""Metadata-only fulfillment authorization consumption custody runtime."""
from __future__ import annotations

import hashlib, json, os, tempfile, threading
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sentientos.control_plane_kernel import AuthorityClass, AdmissionOutcome, ControlActionDecision, ControlActionRequest, ControlPlaneKernel, LifecyclePhase, get_control_plane_kernel
from sentientos.fulfillment_authorization import build_fulfillment_authorization_request, verify_grant_consumption_for_fulfillment, assess_fulfillment_scope_match, build_fulfillment_authorization_consumption_receipt, build_fulfillment_authorization_denial_receipt
from sentientos.local_authorization_grant import LocalAuthorizationGrant, LocalAuthorizationGrantExpiryEvaluation, LocalAuthorizationGrantLedger, LocalAuthorizationGrantRevocationReceipt, LocalAuthorizationGrantVerification, build_local_authorization_grant_expiry_evaluation, local_authorization_grant_digest, local_authorization_grant_expiry_evaluation_digest, local_authorization_grant_ledger_digest, local_authorization_grant_revocation_receipt_digest, local_authorization_grant_verification_digest, verify_local_authorization_grant
from sentientos.world_state_board import WorldStateSourceKind, digest as world_digest

SCHEMA_VERSION = "host_fulfillment_authorization_consumption_custody.v1"
MAX_FUTURE_REQUEST_SECONDS = 24 * 60 * 60
_ALLOWED_BACKENDS = {"metadata_only_future_backend", "future_host_fulfillment_backend"}
_LOCKS: dict[str, threading.Lock] = {}


def _canon(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=lambda o: asdict(o) if hasattr(o, "__dataclass_fields__") else str(o))
def _sha(v: Any) -> str: return "sha256:" + hashlib.sha256(_canon(v).encode()).hexdigest()
def _id(prefix: str, v: Any) -> str: return prefix + hashlib.sha256(_canon(v).encode()).hexdigest()[:24]
def _dict(v: Any) -> dict[str, Any]: return v.to_dict() if hasattr(v, "to_dict") else (asdict(v) if hasattr(v, "__dataclass_fields__") else dict(v))
def _digest_record(p: Mapping[str, Any]) -> str:
    d=dict(p); d["digest"]=""; return _sha(d)
def _parse_time(s: str) -> datetime:
    if s.startswith("expires:"): s=s.removeprefix("expires:")
    if s.startswith("not_before:"): s=s.removeprefix("not_before:")
    if s.startswith("not_after:"): s=s.removeprefix("not_after:")
    dt=datetime.fromisoformat(s.replace("Z","+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
def _now() -> str: return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class HostFulfillmentAuthorizationSource:
    source_id: str; digest: str; issue_receipt_id: str; issue_receipt_digest: str; grant_id: str; grant_digest: str; verification_id: str; verification_digest: str; ledger_id: str; ledger_digest: str; ledger_predecessor_digest: str; expiry_evaluation_id: str; expiry_evaluation_digest: str; revocation_receipt_refs: tuple[Mapping[str, str], ...]; metadata_only: bool=True; no_fulfillment_authority: bool=True; no_effect_authority: bool=True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostFulfillmentAuthorizationRequestEnvelope:
    envelope_id: str; digest: str; source_ref_id: str; source_ref_digest: str; requested_fulfillment_domain: str; requested_backend_class: str; requested_scope_labels: tuple[str,...]; target_labels: tuple[str,...]; requested_time: str; idempotency_key: str; created_at: str; metadata_only: bool=True; request_only: bool=True; fulfillment_granted: bool=False; executor_authorized: bool=False; effect_performed: bool=False; host_mutation_performed: bool=False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostFulfillmentAuthorizationConsumptionPlan:
    plan_id: str; digest: str; envelope_id: str; envelope_digest: str; source_ref_id: str; source_ref_digest: str; recomputed_source_digest: str; idempotency_key: str; expected_ledger_predecessor_digest: str; metadata_only: bool=True; authorizes_fulfillment: bool=False; authorizes_executor: bool=False; grants_privileged_effect_admission: bool=False; invokes_backend: bool=False; effect_performed: bool=False; host_mutation_performed: bool=False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostFulfillmentAuthorizationConsumptionResult:
    status: str; findings: tuple[str,...]; envelope: HostFulfillmentAuthorizationRequestEnvelope; source: HostFulfillmentAuthorizationSource; plan: HostFulfillmentAuthorizationConsumptionPlan|None; admission: Mapping[str,Any]|None; fulfillment_request: Mapping[str,Any]|None; grant_consumption_verification: Mapping[str,Any]|None; scope_assessment: Mapping[str,Any]|None; consumption_receipt: Mapping[str,Any]|None; denial_receipt: Mapping[str,Any]|None; ledger_entry: Mapping[str,Any]|None; ledger: Mapping[str,Any]|None; admission_call_count: int; ledger_append_count: int; replayed: bool=False
    def to_dict(self)->dict[str,Any]: return asdict(self)


def recompute_source(*, issue_receipt: Any, grant: Any, verification: Any, authorization_ledger: Any, ledger_predecessor_digest: str, expiry_evaluation: Any, revocation_receipts: Sequence[Any]=()) -> HostFulfillmentAuthorizationSource:
    issue=_dict(issue_receipt); grant_d=_dict(grant); ver=_dict(verification); led=_dict(authorization_ledger); exp=_dict(expiry_evaluation)
    refs=tuple({"receipt_id": str(_dict(r).get("receipt_id")), "digest": str(_dict(r).get("digest"))} for r in revocation_receipts)
    nested={"issue_receipt_id":issue.get("receipt_id"),"issue_receipt_digest":issue.get("digest"),"grant_id":grant_d.get("grant_id"),"grant_digest":grant_d.get("digest"),"verification_id":ver.get("verification_id"),"verification_digest":ver.get("digest"),"ledger_id":led.get("ledger_id"),"ledger_digest":led.get("digest"),"ledger_predecessor_digest":ledger_predecessor_digest,"expiry_evaluation_id":exp.get("evaluation_id"),"expiry_evaluation_digest":exp.get("digest"),"revocation_receipt_refs":refs,"metadata_only":True,"no_fulfillment_authority":True,"no_effect_authority":True}
    sid=_id("hfac_source_", nested); provisional=HostFulfillmentAuthorizationSource(sid,"",str(nested["issue_receipt_id"]),str(nested["issue_receipt_digest"]),str(nested["grant_id"]),str(nested["grant_digest"]),str(nested["verification_id"]),str(nested["verification_digest"]),str(nested["ledger_id"]),str(nested["ledger_digest"]),str(ledger_predecessor_digest),str(nested["expiry_evaluation_id"]),str(nested["expiry_evaluation_digest"]),refs)
    return replace(provisional, digest=_digest_record(provisional.to_dict()))

def build_request_envelope(source: HostFulfillmentAuthorizationSource, *, requested_fulfillment_domain: str="future_cooling_fulfillment_authorization", requested_backend_class: str="metadata_only_future_backend", requested_scope_labels: Sequence[str] = ("future_cooling_scope",), target_labels: Sequence[str]=(), requested_time: str="1970-01-01T00:00:00+00:00", idempotency_key: str|None=None, created_at: str="1970-01-01T00:00:00+00:00") -> HostFulfillmentAuthorizationRequestEnvelope:
    idem=idempotency_key or _id("hfac_idem_", {"source": source.digest, "domain": requested_fulfillment_domain, "backend": requested_backend_class, "scope": tuple(sorted(requested_scope_labels)), "targets": tuple(sorted(target_labels)), "time": requested_time})
    sem={"source_ref_id":source.source_id,"source_ref_digest":source.digest,"requested_fulfillment_domain":requested_fulfillment_domain,"requested_backend_class":requested_backend_class,"requested_scope_labels":tuple(sorted(requested_scope_labels)),"target_labels":tuple(sorted(target_labels)),"requested_time":requested_time,"idempotency_key":idem,"metadata_only":True,"request_only":True,"fulfillment_granted":False,"executor_authorized":False,"effect_performed":False,"host_mutation_performed":False}
    e0=HostFulfillmentAuthorizationRequestEnvelope(_id("hfac_envelope_", sem),"",source.source_id,source.digest,requested_fulfillment_domain,requested_backend_class,tuple(sorted(requested_scope_labels)),tuple(sorted(target_labels)),requested_time,idem,created_at)
    return replace(e0,digest=_digest_record(e0.to_dict()))

def _validate_source(source: HostFulfillmentAuthorizationSource, supplied: Mapping[str,Any]|None, recomputed: HostFulfillmentAuthorizationSource, *, issue_receipt:Any, grant:Any, verification:Any, ledger:Any, expiry:Any, revocations:Sequence[Any]) -> list[str]:
    f=[]
    if source != recomputed: f.append("source_ref_mismatch")
    if supplied is not None and _dict(supplied) != recomputed.to_dict(): f.append("supplied_source_mismatch")
    checks=[("issue_receipt_digest",_dict(issue_receipt).get("digest")),("grant_digest",_dict(grant).get("digest")),("verification_digest",_dict(verification).get("digest")),("ledger_digest",_dict(ledger).get("digest")),("expiry_evaluation_digest",_dict(expiry).get("digest"))]
    for k,v in checks:
        if getattr(recomputed,k) != v: f.append("nested_"+k+"_mismatch")
    for r, ref in zip(revocations, recomputed.revocation_receipt_refs):
        if _dict(r).get("digest") != ref.get("digest"): f.append("nested_revocation_digest_mismatch")
    return f

def _validate_fresh(*, grant:Any, expiry:Any, request_time:str, current_time:str, max_future_seconds:int=MAX_FUTURE_REQUEST_SECONDS)->list[str]:
    f=[]; g=_dict(grant); e=_dict(expiry)
    try: req=_parse_time(request_time); cur=_parse_time(current_time); exp=_parse_time(str(g.get("expiry_label","")))
    except Exception: return ["time_parse_failed"]
    nbs=[_parse_time(x) for x in g.get("granted_time_bounds",()) if str(x).startswith("not_before:")]
    nas=[_parse_time(x) for x in g.get("granted_time_bounds",()) if str(x).startswith("not_after:")]
    if e.get("grant_id") != g.get("grant_id"): f.append("expiry_evaluation_wrong_grant")
    if e.get("digest") != local_authorization_grant_expiry_evaluation_digest(e): f.append("expiry_digest_mismatch")
    try: ev=_parse_time(str(e.get("evaluated_at")))
    except Exception: f.append("expiry_evaluation_time_invalid"); ev=cur
    if ev > cur: f.append("unsupported_future_expiry_evaluation")
    if str(e.get("expiry_status")) == "local_authorization_expiry_not_expired" and ev < exp <= cur: f.append("stale_non_expired_expiry_evidence")
    if req > exp: f.append("request_after_expiry")
    if cur > exp: f.append("current_clock_after_expiry")
    if nbs and req < max(nbs): f.append("unsupported_backdating")
    if nas and req > min(nas): f.append("request_after_not_after")
    if req > cur + timedelta(seconds=max_future_seconds): f.append("future_request_outside_window")
    if str(e.get("expiry_status")) == "local_authorization_expiry_expired": f.append("expired_grant")
    return f

class HostFulfillmentAuthorizationRuntimeCoordinator:
    def __init__(self, *, runtime_state_root: str|Path|None=None, kernel: ControlPlaneKernel|None=None, clock: Callable[[],str]|None=None) -> None:
        self.runtime_state_root=Path(runtime_state_root or os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT") or (tempfile.gettempdir()+"/sentientos_runtime")); self.kernel=kernel or get_control_plane_kernel(); self.clock=clock or _now; self.admission_call_count=0; self.ledger_append_count=0
    def _root(self)->Path:
        r=(self.runtime_state_root/"host_fulfillment_authorization_consumption_custody").resolve(); r.mkdir(parents=True, exist_ok=True); return r
    def request_consumption_admission(self, plan: HostFulfillmentAuthorizationConsumptionPlan, envelope: HostFulfillmentAuthorizationRequestEnvelope)->ControlActionDecision:
        self.admission_call_count += 1
        return self.kernel.admit(ControlActionRequest("host_fulfillment_authorization_consumption", AuthorityClass.FULFILLMENT_AUTHORIZATION_CONSUMPTION, "operator_invoked_cli", "host_fulfillment_authorization", LifecyclePhase.MAINTENANCE, {"correlation_id":plan.plan_id,"plan_id":plan.plan_id,"plan_digest":plan.digest,"envelope_id":envelope.envelope_id,"envelope_digest":envelope.digest,"metadata_only":True,"grants_fulfillment":False,"authorizes_executor":False,"grants_privileged_effect_admission":False,"invokes_backend":False,"effect_performed":False,"host_mutation_performed":False}))
    def consume(self, *, issue_receipt:Any, grant:Any, verification:Any|None=None, authorization_ledger:Any, ledger_predecessor_digest:str, expiry_evaluation:Any|None=None, revocation_receipts:Sequence[Any]=(), envelope:HostFulfillmentAuthorizationRequestEnvelope, supplied_source:Mapping[str,Any]|None=None, apply:bool=True, admission:ControlActionDecision|None=None)->HostFulfillmentAuthorizationConsumptionResult:
        root=self._root(); lock=_LOCKS.setdefault(str(root), threading.Lock())
        with lock:
            cur=self.clock(); exp=expiry_evaluation or build_local_authorization_grant_expiry_evaluation(grant, evaluated_at=cur)
            ver=verification or verify_local_authorization_grant(grant, checked_scope_labels=envelope.requested_scope_labels, checked_time_label=envelope.requested_time, expiry_evaluation=exp, revocation_receipts=revocation_receipts)
            source=recompute_source(issue_receipt=issue_receipt, grant=grant, verification=ver, authorization_ledger=authorization_ledger, ledger_predecessor_digest=ledger_predecessor_digest, expiry_evaluation=exp, revocation_receipts=revocation_receipts)
            findings=[]
            if envelope.source_ref_id != source.source_id or envelope.source_ref_digest != source.digest: findings.append("envelope_source_ref_mismatch")
            findings += _validate_source(source, supplied_source, source, issue_receipt=issue_receipt, grant=grant, verification=ver, ledger=authorization_ledger, expiry=exp, revocations=revocation_receipts)
            if _dict(grant).get("digest") != local_authorization_grant_digest(grant): findings.append("grant_digest_mismatch")
            if _dict(ver).get("digest") != local_authorization_grant_verification_digest(ver): findings.append("grant_verification_digest_mismatch")
            if _dict(authorization_ledger).get("digest") != local_authorization_grant_ledger_digest(authorization_ledger): findings.append("authorization_ledger_digest_mismatch")
            findings += _validate_fresh(grant=grant, expiry=exp, request_time=envelope.requested_time, current_time=cur)
            if any(_dict(r).get("revocation_status") == "local_authorization_revocation_recorded" for r in revocation_receipts): findings.append("grant_revoked")
            if set(envelope.requested_scope_labels) - set(_dict(grant).get("granted_scope_labels",())): findings.append("scope_expansion")
            if set(envelope.target_labels) - set(_dict(grant).get("granted_scope_labels",())) - set(_dict(grant).get("target_labels",())): findings.append("target_expansion")
            if envelope.requested_backend_class not in _ALLOWED_BACKENDS: findings.append("backend_label_rejected")
            current_ledger_path=root/"consumption_ledger.json"; entries=[]
            if current_ledger_path.exists(): entries=json.loads(current_ledger_path.read_text()).get("entries",[])
            current_pred=_sha(entries) if entries else "sha256:empty"
            if ledger_predecessor_digest != _dict(authorization_ledger).get("digest") and ledger_predecessor_digest != "sha256:empty": findings.append("forged_ledger_predecessor")
            plan=None
            if not findings:
                plan0=HostFulfillmentAuthorizationConsumptionPlan(_id("hfac_plan_", {"envelope":envelope.digest,"source":source.digest,"pred":current_pred}),"",envelope.envelope_id,envelope.digest,source.source_id,source.digest,source.digest,envelope.idempotency_key,current_pred)
                plan=replace(plan0,digest=_digest_record(plan0.to_dict()))
                idx_path=root/"idempotency_index.json"; idx=json.loads(idx_path.read_text()) if idx_path.exists() else {}
                semantic={"envelope":envelope.digest,"source":source.digest,"grant":_dict(grant).get("digest"),"scope":envelope.requested_scope_labels,"targets":envelope.target_labels,"backend":envelope.requested_backend_class,"time":envelope.requested_time}
                prior=idx.get(envelope.idempotency_key)
                if prior and prior.get("semantic") != json.loads(_canon(semantic)): findings.append("idempotency_conflict")
                elif prior:
                    return HostFulfillmentAuthorizationConsumptionResult("recorded",(),envelope,source,plan,prior.get("admission"),prior.get("fulfillment_request"),prior.get("grant_consumption_verification"),prior.get("scope_assessment"),prior.get("consumption_receipt"),None,prior.get("ledger_entry"),{"entries":entries,"entry_count":len(entries),"digest":current_pred},self.admission_call_count,self.ledger_append_count,True)
            if findings:
                den_req=build_fulfillment_authorization_request(grant, ver, requested_fulfillment_domain=envelope.requested_fulfillment_domain, requested_backend_class=envelope.requested_backend_class, requested_scope_labels=envelope.requested_scope_labels, requested_time_label=envelope.requested_time, request_id=envelope.envelope_id, created_at=cur)
                denial=build_fulfillment_authorization_denial_receipt(den_req, created_at=cur).to_dict(); denial["denial_reason_codes"]=tuple(sorted(set(denial["denial_reason_codes"])|set(findings)))
                return HostFulfillmentAuthorizationConsumptionResult("denied",tuple(findings),envelope,source,plan,None,den_req.to_dict(),None,None,None,denial,None,None,self.admission_call_count,self.ledger_append_count)
            assert plan is not None
            admission = admission or self.request_consumption_admission(plan, envelope)
            if not admission.allowed or admission.authority_class != AuthorityClass.FULFILLMENT_AUTHORIZATION_CONSUMPTION:
                req=build_fulfillment_authorization_request(grant, ver, requested_fulfillment_domain=envelope.requested_fulfillment_domain, requested_backend_class=envelope.requested_backend_class, requested_scope_labels=envelope.requested_scope_labels, requested_time_label=envelope.requested_time, request_id=envelope.envelope_id, created_at=cur)
                denial_receipt=build_fulfillment_authorization_denial_receipt(req, created_at=cur)
                return HostFulfillmentAuthorizationConsumptionResult("denied",("consumption_admission_not_allowed",),envelope,source,plan,admission.to_dict(),req.to_dict(),None,None,None,denial_receipt.to_dict(),None,None,self.admission_call_count,self.ledger_append_count)
            req=build_fulfillment_authorization_request(grant, ver, requested_fulfillment_domain=envelope.requested_fulfillment_domain, requested_backend_class=envelope.requested_backend_class, requested_scope_labels=envelope.requested_scope_labels, requested_time_label=envelope.requested_time, request_id=envelope.envelope_id, created_at=cur)
            gcv=verify_grant_consumption_for_fulfillment(grant, ver, req); ass=assess_fulfillment_scope_match(grant, req); rec=build_fulfillment_authorization_consumption_receipt(req,gcv,ass,created_at=cur)
            if rec.consumption_status not in {"fulfillment_authorization_consumption_recorded","fulfillment_authorization_consumption_recorded_with_warnings"}:
                denial_receipt=build_fulfillment_authorization_denial_receipt(req,gcv,ass,created_at=cur)
                return HostFulfillmentAuthorizationConsumptionResult("denied",(rec.consumption_status,),envelope,source,plan,admission.to_dict(),req.to_dict(),gcv.to_dict(),ass.to_dict(),None,denial_receipt.to_dict(),None,None,self.admission_call_count,self.ledger_append_count)
            entry={"entry_id":_id("hfac_entry_", {"plan":plan.digest,"receipt":rec.digest}),"digest":"","source":source.to_dict(),"plan":plan.to_dict(),"admission":admission.to_dict(),"fulfillment_request":req.to_dict(),"grant_consumption_verification":gcv.to_dict(),"scope_assessment":ass.to_dict(),"consumption_receipt":rec.to_dict(),"created_at":cur,"metadata_only":True,"fulfillment_granted":False,"executor_authorized":False,"effect_performed":False,"host_mutation_performed":False}
            entry["digest"]=_digest_record(entry)
            if apply:
                entries.append(entry); self.ledger_append_count += 1
                ledger={"schema_version":SCHEMA_VERSION,"entries":entries,"entry_count":len(entries),"digest":_sha(entries),"metadata_only":True,"fulfillment_granted":False,"effect_performed":False,"host_mutation_performed":False}
                current_ledger_path.write_text(json.dumps(ledger, sort_keys=True, indent=2), encoding="utf-8")
                idx_path=root/"idempotency_index.json"; idx=json.loads(idx_path.read_text()) if idx_path.exists() else {}; idx[envelope.idempotency_key]={"semantic":json.loads(_canon(semantic)),"admission":admission.to_dict(),"fulfillment_request":req.to_dict(),"grant_consumption_verification":gcv.to_dict(),"scope_assessment":ass.to_dict(),"consumption_receipt":rec.to_dict(),"ledger_entry":entry}; idx_path.write_text(json.dumps(idx,sort_keys=True,indent=2),encoding="utf-8")
            else: ledger={"entries":entries,"entry_count":len(entries),"digest":_sha(entries) if entries else "sha256:empty"}
            return HostFulfillmentAuthorizationConsumptionResult("recorded",(),envelope,source,plan,admission.to_dict(),req.to_dict(),gcv.to_dict(),ass.to_dict(),rec.to_dict(),None,entry,ledger,self.admission_call_count,self.ledger_append_count)

def world_state_records(result: HostFulfillmentAuthorizationConsumptionResult, *, observed_at: str="1970-01-01T00:00:00+00:00")->list[dict[str,Any]]:
    out=[]
    for stage,kind,obj in (("request","host_fulfillment_authorization_request_envelope",result.envelope),("source","host_fulfillment_authorization_source",result.source),("admission_candidate","host_fulfillment_authorization_consumption_plan",result.plan),("admission","host_fulfillment_authorization_consumption_admission",result.admission),("verification","host_fulfillment_authorization_grant_consumption_verification",result.grant_consumption_verification),("assessment","host_fulfillment_authorization_scope_assessment",result.scope_assessment),("receipt","host_fulfillment_authorization_consumption_receipt",result.consumption_receipt or result.denial_receipt),("ledger","host_fulfillment_authorization_consumption_ledger_entry",result.ledger_entry),("ledger","host_fulfillment_authorization_consumption_ledger",result.ledger)):
        if obj is None: continue
        p=_dict(obj); p.update({"fulfillment_granted":False,"executor_authorized":False,"effect_claimed":False,"effect_proven":False,"host_mutation_performed":False})
        sid=str(p.get("envelope_id") or p.get("source_id") or p.get("plan_id") or p.get("correlation_id") or p.get("verification_id") or p.get("assessment_id") or p.get("receipt_id") or p.get("entry_id") or "host_fulfillment_authorization_ledger")
        out.append({"source_kind":WorldStateSourceKind.PRIVILEGE.value,"schema_version":SCHEMA_VERSION,"observed_at":observed_at,"source_id":f"hfac:{sid}:{kind}","subject_id":sid,"subject_kind":kind,"stage":stage,"disposition":"allow" if kind.endswith("admission") and p.get("outcome")=="allow" else ("deny" if result.status=="denied" and kind.endswith(("receipt","admission")) else result.status),"evidence_strength":"recorded","payload":p,"effect_claimed":False,"effect_proven":False,"digest":world_digest(p)})
    return out

def dashboard_projection(records: Sequence[Mapping[str,Any]])->dict[str,Any]:
    stages: dict[str, int] = {}; latest: list[str] = []; denied=recorded=0
    for rec in records:
        stage=str(rec.get("stage","unknown")); stages[stage]=stages.get(stage,0)+1; latest.append(str(rec.get("subject_id","")))
        if rec.get("disposition")=="deny": denied+=1
        if rec.get("disposition")=="recorded": recorded+=1
    return {"status":"recorded" if records else "unavailable","fact_count":len(records),"stage_counts":stages,"recorded_consumption_count":recorded,"denial_count":denied,"latest_ids":[x for x in latest[-20:] if x],"read_only":True,"metadata_only":True,"explicit_request_required":True,"exact_active_grant_evidence_required":True,"current_expiry_and_revocation_checks_required":True,"dedicated_metadata_consumption_admission_required":True,"automatic_daemon_consumption":False,"fulfillment_granted":False,"executor_authorized":False,"privileged_effect_admission_granted":False,"backend_invoked":False,"execution_triggered":False,"host_mutation_performed":False,"effect_proven":False}
