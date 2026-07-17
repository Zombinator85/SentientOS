# mypy: disable-error-code="arg-type"
"""Explicit local authorization grant custody runtime.

Binds host live-grant readiness evidence to independent operator/policy
approval records, a dedicated local-authority-record control-plane admission,
scoped expiring local authorization grant metadata, and append-only revocation
ledger evidence. This module never authorizes fulfillment or host effects.
"""
from __future__ import annotations

import hashlib, json, os, tempfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sentientos.control_plane_kernel import AuthorityClass, AdmissionOutcome, ControlActionDecision, ControlActionRequest, ControlPlaneKernel, LifecyclePhase, get_control_plane_kernel
from sentientos.host_live_grant_readiness_runtime import HostLiveGrantReadinessEvaluation, validate_evaluation as validate_readiness_evaluation
from sentientos.local_authorization_grant import (
    LocalAuthorizationGrant, LocalAuthorizationGrantExpiryEvaluation, LocalAuthorizationGrantLedger,
    LocalAuthorizationGrantRevocationReceipt, LocalAuthorizationGrantVerification,
    build_local_authorization_grant, build_local_authorization_grant_expiry_evaluation,
    build_local_authorization_grant_ledger, build_local_authorization_grant_revocation_receipt,
    local_authorization_grant_digest, verify_local_authorization_grant,
    validate_local_authorization_grant, validate_local_authorization_grant_ledger,
)
from sentientos.world_state_board import WorldStateSourceKind, digest as world_digest

SCHEMA_VERSION = "host_local_authorization_grant_custody.v1"
DECISION_DISPOSITIONS = frozenset({"approve", "reject", "defer"})
BAD_IDENTITIES = frozenset({"", "*", "sample", "sample_operator", "sample_policy", "demo", "default", "anonymous", "placeholder", "test"})
NO_EFFECT_FLAGS = {
    "metadata_only": True, "local_authority_metadata_only": True, "operator_approval_granted": False,
    "policy_approval_granted": False, "grant_issued": False, "fulfillment_granted": False,
    "effect_performed": False, "effect_claimed": False, "effect_proven": False,
    "host_mutation_performed": False, "execution_triggered": False,
}

def _canon(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=lambda o: asdict(o) if hasattr(o, "__dataclass_fields__") else str(o))
def _sha(v: Any) -> str: return "sha256:" + hashlib.sha256(_canon(v).encode()).hexdigest()
def _id(prefix: str, v: Any) -> str: return prefix + hashlib.sha256(_canon(v).encode()).hexdigest()[:24]
def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _dict(v: Any) -> dict[str, Any]: return v.to_dict() if hasattr(v, "to_dict") else (asdict(v) if hasattr(v, "__dataclass_fields__") else dict(v))
def _tuple(v: Sequence[str] | None) -> tuple[str, ...]: return tuple(str(x) for x in (v or ()))
def _semantic(payload: Mapping[str, Any], *exclude: str) -> dict[str, Any]:
    excluded = set(exclude) | {"created_at", "observed_at", "artifact_root", "artifact_paths", "output_path", "runtime_state_root", "pid", "dashboard_request_time"}
    return {k: v for k, v in payload.items() if k not in excluded and not k.endswith("_path")}

def _digest_record(payload: Mapping[str, Any]) -> str:
    p = dict(payload); p["digest"] = ""; return _sha(p)

@dataclass(frozen=True)
class HostLocalAuthorizationValidationResult:
    ok: bool; status: str; findings: tuple[str, ...] = ()
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostLocalAuthorizationReviewRequest:
    schema_version: str; request_id: str; digest: str; source_readiness_evaluation_id: str; source_readiness_evaluation_digest: str; prerequisite_matrix_id: str; prerequisite_matrix_digest: str; approval_request_packet_id: str; approval_request_packet_digest: str; grant_preflight_receipt_id: str; grant_preflight_receipt_digest: str; denial_deferral_receipt_id: str; denial_deferral_receipt_digest: str; readiness_domain: str; requested_authorization_domain: str; requested_scope: str; target_labels: tuple[str, ...]; satisfied_prerequisites: tuple[str, ...]; conditional_prerequisites: tuple[str, ...]; missing_prerequisites: tuple[str, ...]; blocked_prerequisites: tuple[str, ...]; contradicted_prerequisites: tuple[str, ...]; blocked_actions: tuple[str, ...]; not_before: str; not_after: str; expiry: str; revocation_posture: tuple[str, ...]; source_tick_id: str; correlation_id: str; max_review_lifetime_seconds: int; created_at: str; operator_approval_granted: bool=False; policy_approval_granted: bool=False; grant_issued: bool=False; fulfillment_granted: bool=False; effect_performed: bool=False; host_mutation_performed: bool=False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class _DecisionBase:
    schema_version: str; decision_id: str; digest: str; review_request_id: str; review_request_digest: str; readiness_evaluation_id: str; readiness_evaluation_digest: str; prerequisite_matrix_id: str; prerequisite_matrix_digest: str; authorization_domain: str; scope: str; target_labels: tuple[str, ...]; not_before: str; not_after: str; expiry: str; identity: str; role_or_policy_version: str; disposition: str; reason_codes: tuple[str, ...]; note: str; custody_timestamp: str; metadata_only: bool=True; approval_enables_issuance_request_only: bool=True; fulfillment_granted: bool=False; effect_performed: bool=False; host_mutation_performed: bool=False
    def to_dict(self) -> dict[str, Any]: return asdict(self)
class OperatorLocalAuthorizationDecision(_DecisionBase): pass
class PolicyLocalAuthorizationDecision(_DecisionBase): pass

@dataclass(frozen=True)
class HostLocalAuthorizationIssuePlan:
    schema_version: str; plan_id: str; digest: str; request_id: str; request_digest: str; operator_decision_id: str; operator_decision_digest: str; policy_decision_id: str; policy_decision_digest: str; intended_grant_id: str; authorization_domain: str; scope: str; target_labels: tuple[str, ...]; not_before: str; not_after: str; expiry: str; revocation_path: tuple[str, ...]; prior_ledger_digest: str; expected_ledger_state: str; idempotency_key: str; attempt_id: str; runtime_supervisor_posture: str; safety_lineage: Mapping[str, Any]; metadata_only: bool=True; authorizes_fulfillment: bool=False; effect_performed: bool=False; host_mutation_performed: bool=False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostLocalAuthorizationIssueReceipt:
    schema_version: str; receipt_id: str; digest: str; issue_status: str; request_id: str; request_digest: str; plan_id: str; plan_digest: str; admission_decision_ref: str; admission_outcome: str; grant_id: str; grant_digest: str; ledger_id: str; ledger_digest: str; idempotency_key: str; attempt_id: str; created_at: str; replayed: bool=False; live_authorization_granted: bool=False; fulfillment_granted: bool=False; effect_performed: bool=False; host_mutation_performed: bool=False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostLocalAuthorizationRevocationDecision:
    schema_version: str; decision_id: str; digest: str; grant_id: str; grant_digest: str; current_ledger_digest: str; identity: str; reason_codes: tuple[str, ...]; effective_at: str; custody_timestamp: str; metadata_only: bool=True; reduces_authority_only: bool=True; authorizes_fulfillment: bool=False; effect_performed: bool=False; host_mutation_performed: bool=False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostLocalAuthorizationRevocationReceipt:
    schema_version: str; receipt_id: str; digest: str; revocation_status: str; decision_id: str; decision_digest: str; grant_id: str; grant_digest: str; ledger_id: str; ledger_digest: str; local_revocation_receipt_id: str; local_revocation_receipt_digest: str; created_at: str; replayed: bool=False; authorizes_fulfillment: bool=False; effect_performed: bool=False; host_mutation_performed: bool=False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostLocalAuthorizationLedgerSnapshot:
    schema_version: str; snapshot_id: str; digest: str; ledger: LocalAuthorizationGrantLedger; issue_receipts: tuple[HostLocalAuthorizationIssueReceipt, ...]; revocation_receipts: tuple[HostLocalAuthorizationRevocationReceipt, ...]; active_count: int; expired_count: int; revoked_count: int; conflicted_count: int; created_at: str; metadata_only: bool=True; fulfillment_granted: bool=False; effect_performed: bool=False; host_mutation_performed: bool=False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

def build_review_request(evaluation: HostLiveGrantReadinessEvaluation, *, requested_authorization_domain: str="future_cooling_local_authorization", requested_scope: str="future_cooling_scope", target_labels: Sequence[str], not_before: str, not_after: str, expiry: str, revocation_posture: Sequence[str] = ("revocable:host_local_authorization_revocation",), max_review_lifetime_seconds: int=3600, created_at: str="1970-01-01T00:00:00+00:00") -> HostLocalAuthorizationReviewRequest:
    val = validate_readiness_evaluation(evaluation)
    if not val.ok or evaluation.summary.status in {"blocked", "contradicted", "unavailable"}: raise ValueError("readiness_not_eligible")
    if not not_before or not not_after or not expiry: raise ValueError("missing_time_bounds")
    item = next((i for i in evaluation.items if i.readiness_records), None)
    if item is None or item.readiness_records is None: raise ValueError("missing_readiness_records")
    rec = item.readiness_records
    if getattr(rec.preflight_receipt, "live_authorization_granted", False) or getattr(rec.preflight_receipt, "fulfillment_granted", False): raise ValueError("upstream_authority_claim")
    sem = {"schema_version": SCHEMA_VERSION, "source_readiness_evaluation_id": evaluation.evaluation_id, "source_readiness_evaluation_digest": evaluation.semantic_digest, "prerequisite_matrix_id": rec.prerequisite_matrix.matrix_id, "prerequisite_matrix_digest": rec.prerequisite_matrix.digest, "approval_request_packet_id": rec.approval_packet.packet_id, "approval_request_packet_digest": rec.approval_packet.digest, "grant_preflight_receipt_id": rec.preflight_receipt.receipt_id, "grant_preflight_receipt_digest": rec.preflight_receipt.digest, "denial_deferral_receipt_id": rec.denial_deferral_receipt.receipt_id, "denial_deferral_receipt_digest": rec.denial_deferral_receipt.digest, "readiness_domain": rec.preflight_receipt.readiness_domain, "requested_authorization_domain": requested_authorization_domain, "requested_scope": requested_scope, "target_labels": tuple(sorted(target_labels)), "satisfied_prerequisites": tuple(sorted(rec.prerequisite_matrix.satisfied_labels)), "conditional_prerequisites": tuple(sorted(getattr(rec.prerequisite_matrix, "conditional_labels", ()))), "missing_prerequisites": tuple(sorted(rec.prerequisite_matrix.missing_labels)), "blocked_prerequisites": tuple(sorted(getattr(rec.prerequisite_matrix, "blocked_labels", ()))), "contradicted_prerequisites": tuple(sorted(getattr(rec.prerequisite_matrix, "contradicted_labels", ()))), "blocked_actions": tuple(sorted(rec.prerequisite_matrix.blocked_actions)), "not_before": not_before, "not_after": not_after, "expiry": expiry, "revocation_posture": tuple(sorted(revocation_posture)), "source_tick_id": evaluation.source_tick_id, "correlation_id": evaluation.correlation_id, "max_review_lifetime_seconds": max_review_lifetime_seconds, **NO_EFFECT_FLAGS}
    rid = _id("hlarq_", sem); provisional = HostLocalAuthorizationReviewRequest(SCHEMA_VERSION, rid, "", sem["source_readiness_evaluation_id"], sem["source_readiness_evaluation_digest"], sem["prerequisite_matrix_id"], sem["prerequisite_matrix_digest"], sem["approval_request_packet_id"], sem["approval_request_packet_digest"], sem["grant_preflight_receipt_id"], sem["grant_preflight_receipt_digest"], sem["denial_deferral_receipt_id"], sem["denial_deferral_receipt_digest"], sem["readiness_domain"], requested_authorization_domain, requested_scope, sem["target_labels"], sem["satisfied_prerequisites"], sem["conditional_prerequisites"], sem["missing_prerequisites"], sem["blocked_prerequisites"], sem["contradicted_prerequisites"], sem["blocked_actions"], not_before, not_after, expiry, sem["revocation_posture"], evaluation.source_tick_id, evaluation.correlation_id, max_review_lifetime_seconds, created_at)
    return replace(provisional, digest=_digest_record(provisional.to_dict()))

def validate_review_request(request: HostLocalAuthorizationReviewRequest | Mapping[str, Any]) -> HostLocalAuthorizationValidationResult:
    p=_dict(request); f=[]
    if p.get("schema_version") != SCHEMA_VERSION: f.append("unknown_schema")
    if p.get("digest") != _digest_record(p): f.append("digest_mismatch")
    if p.get("operator_approval_granted") or p.get("policy_approval_granted") or p.get("grant_issued") or p.get("fulfillment_granted") or p.get("effect_performed") or p.get("host_mutation_performed"): f.append("forbidden_authority_claim")
    if p.get("blocked_prerequisites") or p.get("contradicted_prerequisites"): f.append("readiness_not_complete")
    if not p.get("not_before") or not p.get("not_after") or not p.get("expiry"): f.append("missing_time_bounds")
    return HostLocalAuthorizationValidationResult(not f, "valid" if not f else "malformed", tuple(f))

def _decision(cls: type[_DecisionBase], request: HostLocalAuthorizationReviewRequest, *, identity: str, role_or_policy_version: str, disposition: str, reason_codes: Sequence[str], note: str="", custody_timestamp: str="1970-01-01T00:00:00+00:00") -> _DecisionBase:
    if disposition not in DECISION_DISPOSITIONS: raise ValueError("unknown_disposition")
    sem={"schema_version":SCHEMA_VERSION,"kind":cls.__name__,"review_request_id":request.request_id,"review_request_digest":request.digest,"readiness_evaluation_id":request.source_readiness_evaluation_id,"readiness_evaluation_digest":request.source_readiness_evaluation_digest,"prerequisite_matrix_id":request.prerequisite_matrix_id,"prerequisite_matrix_digest":request.prerequisite_matrix_digest,"authorization_domain":request.requested_authorization_domain,"scope":request.requested_scope,"target_labels":request.target_labels,"not_before":request.not_before,"not_after":request.not_after,"expiry":request.expiry,"identity":identity,"role_or_policy_version":role_or_policy_version,"disposition":disposition,"reason_codes":tuple(sorted(reason_codes)),"note":note,"metadata_only":True,"approval_enables_issuance_request_only":True,"fulfillment_granted":False,"effect_performed":False,"host_mutation_performed":False}
    did=_id("hlad_", sem); provisional=cls(SCHEMA_VERSION,did,"",request.request_id,request.digest,request.source_readiness_evaluation_id,request.source_readiness_evaluation_digest,request.prerequisite_matrix_id,request.prerequisite_matrix_digest,request.requested_authorization_domain,request.requested_scope,request.target_labels,request.not_before,request.not_after,request.expiry,identity,role_or_policy_version,disposition,tuple(sorted(reason_codes)),note,custody_timestamp)
    return replace(provisional, digest=_digest_record(provisional.to_dict()))

def build_operator_decision(request: HostLocalAuthorizationReviewRequest, **kw: Any) -> OperatorLocalAuthorizationDecision: return _decision(OperatorLocalAuthorizationDecision, request, **kw)  # type: ignore[return-value]
def build_policy_decision(request: HostLocalAuthorizationReviewRequest, **kw: Any) -> PolicyLocalAuthorizationDecision: return _decision(PolicyLocalAuthorizationDecision, request, **kw)  # type: ignore[return-value]

def validate_decision(decision: _DecisionBase | Mapping[str, Any], request: HostLocalAuthorizationReviewRequest | Mapping[str, Any] | None=None, *, strict_identity: bool=True, now: str="1970-01-01T00:00:00+00:00") -> HostLocalAuthorizationValidationResult:
    p=_dict(decision); f=[]
    if p.get("schema_version") != SCHEMA_VERSION: f.append("unknown_schema")
    if p.get("digest") != _digest_record(p): f.append("digest_mismatch")
    if p.get("disposition") not in DECISION_DISPOSITIONS: f.append("unknown_disposition")
    if strict_identity and str(p.get("identity", "")).lower() in BAD_IDENTITIES: f.append("placeholder_identity")
    not_after = str(p.get("not_after") or "")
    if not_after and now > not_after: f.append("decision_expired")
    if p.get("fulfillment_granted") or p.get("effect_performed") or p.get("host_mutation_performed"): f.append("forbidden_effect_claim")
    if request is not None:
        r=_dict(request)
        for a,b in (("review_request_id","request_id"),("review_request_digest","digest"),("authorization_domain","requested_authorization_domain"),("scope","requested_scope"),("target_labels","target_labels"),("not_before","not_before"),("not_after","not_after"),("expiry","expiry")):
            if p.get(a) != r.get(b): f.append(f"request_binding_mismatch:{a}")
    return HostLocalAuthorizationValidationResult(not f, "valid" if not f else "malformed", tuple(f))

def build_issue_plan(request: HostLocalAuthorizationReviewRequest, operator_decision: OperatorLocalAuthorizationDecision, policy_decision: PolicyLocalAuthorizationDecision, *, prior_ledger_digest: str="sha256:empty", idempotency_key: str|None=None, attempt_id: str|None=None, runtime_supervisor_posture: str="observed_no_host_effect", created_at: str="1970-01-01T00:00:00+00:00") -> HostLocalAuthorizationIssuePlan:
    if validate_review_request(request).ok is not True: raise ValueError("invalid_request")
    for d in (operator_decision, policy_decision):
        v=validate_decision(d, request)
        if not v.ok or d.disposition != "approve": raise ValueError("decision_not_approved")
    intended=_id("hlar_grant_", {"request":request.digest,"operator":operator_decision.digest,"policy":policy_decision.digest,"domain":request.requested_authorization_domain,"scope":request.requested_scope,"targets":request.target_labels,"bounds":(request.not_before,request.not_after),"expiry":request.expiry})
    idem=idempotency_key or _id("hlar_idem_", {"request":request.digest,"operator":operator_decision.digest,"policy":policy_decision.digest})
    att=attempt_id or _id("hlar_attempt_", {"idempotency_key":idem,"prior_ledger_digest":prior_ledger_digest})
    sem={"schema_version":SCHEMA_VERSION,"request_id":request.request_id,"request_digest":request.digest,"operator_decision_id":operator_decision.decision_id,"operator_decision_digest":operator_decision.digest,"policy_decision_id":policy_decision.decision_id,"policy_decision_digest":policy_decision.digest,"intended_grant_id":intended,"authorization_domain":request.requested_authorization_domain,"scope":request.requested_scope,"target_labels":request.target_labels,"not_before":request.not_before,"not_after":request.not_after,"expiry":request.expiry,"revocation_path":request.revocation_posture,"prior_ledger_digest":prior_ledger_digest,"expected_ledger_state":"append_one_issue_if_admitted","idempotency_key":idem,"attempt_id":att,"runtime_supervisor_posture":runtime_supervisor_posture,"safety_lineage":{"readiness_evaluation_id":request.source_readiness_evaluation_id,"readiness_evaluation_digest":request.source_readiness_evaluation_digest,"prerequisite_matrix_id":request.prerequisite_matrix_id,"prerequisite_matrix_digest":request.prerequisite_matrix_digest},"metadata_only":True,"authorizes_fulfillment":False,"effect_performed":False,"host_mutation_performed":False}
    pid=_id("hlarp_", sem); lineage: Mapping[str, Any] = {"readiness_evaluation_id":request.source_readiness_evaluation_id,"readiness_evaluation_digest":request.source_readiness_evaluation_digest,"prerequisite_matrix_id":request.prerequisite_matrix_id,"prerequisite_matrix_digest":request.prerequisite_matrix_digest}
    provisional=HostLocalAuthorizationIssuePlan(SCHEMA_VERSION,pid,"",request.request_id,request.digest,operator_decision.decision_id,operator_decision.digest,policy_decision.decision_id,policy_decision.digest,intended,request.requested_authorization_domain,request.requested_scope,request.target_labels,request.not_before,request.not_after,request.expiry,request.revocation_posture,prior_ledger_digest,"append_one_issue_if_admitted",idem,att,runtime_supervisor_posture,lineage)
    return replace(provisional, digest=_digest_record(provisional.to_dict()))

def validate_plan(plan: HostLocalAuthorizationIssuePlan | Mapping[str, Any]) -> HostLocalAuthorizationValidationResult:
    p=_dict(plan); f=[]
    if p.get("schema_version") != SCHEMA_VERSION: f.append("unknown_schema")
    if p.get("digest") != _digest_record(p): f.append("digest_mismatch")
    if p.get("authorizes_fulfillment") or p.get("effect_performed") or p.get("host_mutation_performed"): f.append("forbidden_effect_claim")
    if not p.get("idempotency_key") or not p.get("attempt_id"): f.append("missing_idempotency")
    return HostLocalAuthorizationValidationResult(not f, "valid" if not f else "malformed", tuple(f))

class HostLocalAuthorizationRuntimeCoordinator:
    def __init__(self, *, runtime_state_root: str|Path|None=None, kernel: ControlPlaneKernel|None=None, clock: Callable[[], str]|None=None) -> None:
        self.runtime_state_root=Path(runtime_state_root or os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT") or (tempfile.gettempdir()+"/sentientos_runtime")); self.kernel=kernel or get_control_plane_kernel(); self.clock=clock or _now; self.issue_call_count=0; self.revoke_call_count=0
    def _root(self) -> Path:
        r=self.runtime_state_root.resolve(); r.mkdir(parents=True, exist_ok=True)
        if r.is_symlink(): raise ValueError("symlink_runtime_root")
        return r/"host_local_authorization_grant_custody"
    def request_issue_admission(self, plan: HostLocalAuthorizationIssuePlan, request: HostLocalAuthorizationReviewRequest, operator: OperatorLocalAuthorizationDecision, policy: PolicyLocalAuthorizationDecision) -> ControlActionDecision:
        return self.kernel.admit(ControlActionRequest("host_local_authorization_grant_issuance", AuthorityClass.LOCAL_AUTHORIZATION_GRANT_ISSUANCE, "operator_invoked_cli", "host_local_authorization", LifecyclePhase.MAINTENANCE, {"correlation_id":plan.attempt_id,"plan_id":plan.plan_id,"plan_digest":plan.digest,"request_id":request.request_id,"request_digest":request.digest,"operator_decision_id":operator.decision_id,"operator_decision_digest":operator.digest,"policy_decision_id":policy.decision_id,"policy_decision_digest":policy.digest,"current_ledger_digest":plan.prior_ledger_digest,"idempotency_key":plan.idempotency_key,"metadata_only":True,"grants_fulfillment":False,"grants_privileged_effect_admission":False}))
    def _load_ledger(self) -> tuple[list[LocalAuthorizationGrant], list[LocalAuthorizationGrantRevocationReceipt], list[LocalAuthorizationGrantExpiryEvaluation], list[HostLocalAuthorizationIssueReceipt], list[HostLocalAuthorizationRevocationReceipt], str]:
        path=self._root()/"ledger_snapshot.json"
        if not path.exists(): return [], [], [], [], [], "sha256:empty"
        data=json.loads(path.read_text())
        # Return digest only for conflict checks; authoritative records are reconstructed during current process tests via JSON maps when needed.
        return [], [], [], [], [], str(data.get("digest", "sha256:empty"))
    def issue(self, request: HostLocalAuthorizationReviewRequest, operator: OperatorLocalAuthorizationDecision, policy: PolicyLocalAuthorizationDecision, plan: HostLocalAuthorizationIssuePlan, *, apply: bool=False, admission: ControlActionDecision|None=None) -> HostLocalAuthorizationIssueReceipt:
        self.issue_call_count += 1
        for v in (validate_review_request(request), validate_decision(operator, request, now=self.clock()), validate_decision(policy, request, now=self.clock()), validate_plan(plan)):
            if not v.ok: raise ValueError(";".join(v.findings))
        if operator.disposition != "approve" or policy.disposition != "approve": raise ValueError("decision_not_approved_zero_writes")
        if not apply: raise RuntimeError("not_applied")
        root=self._root(); root.mkdir(parents=True, exist_ok=True)
        index_path=root/"idempotency_index.json"; index=json.loads(index_path.read_text()) if index_path.exists() else {}
        sem={"request":request.digest,"operator":operator.digest,"policy":policy.digest,"plan":plan.digest}
        prior=index.get(plan.idempotency_key)
        if prior:
            if prior.get("semantic") != sem: raise ValueError("conflicting_idempotency_key")
            data=dict(prior["receipt"]); data["replayed"] = True; return HostLocalAuthorizationIssueReceipt(**data)
        admission=admission or self.request_issue_admission(plan, request, operator, policy)
        if not admission.allowed or admission.authority_class != AuthorityClass.LOCAL_AUTHORIZATION_GRANT_ISSUANCE: raise PermissionError("issuance_admission_not_allowed_zero_writes")
        op_ev={"evidence_id":operator.decision_id,"digest":operator.digest,"approval_status":"approval_evidence_present","approval_scope_labels":operator.target_labels+(operator.scope,),"approval_time_bounds":(operator.not_before,operator.not_after),"approval_expiry_label":"expires:"+operator.expiry,"approval_revocation_label":"revocable:host_local_authorization_revocation","warning_codes":(),"risk_codes":()}
        pol_ev={"evidence_id":policy.decision_id,"digest":policy.digest,"approval_status":"approval_evidence_present","policy_scope_labels":policy.target_labels+(policy.scope,),"policy_time_bounds":(policy.not_before,policy.not_after),"policy_expiry_label":"expires:"+policy.expiry,"policy_revocation_label":"revocable:host_local_authorization_revocation","warning_codes":(),"risk_codes":()}
        pre={"receipt_id":request.grant_preflight_receipt_id,"digest":request.grant_preflight_receipt_digest,"preflight_status":"grant_issue_preflight_recorded","readiness_status":"live_grant_readiness_ready_for_operator_policy_review","readiness_domain":request.readiness_domain,"blocked_actions":request.blocked_actions,"warning_codes":(),"risk_codes":()}
        mat={"matrix_id":request.prerequisite_matrix_id,"digest":request.prerequisite_matrix_digest,"readiness_domain":request.readiness_domain,"blocked_actions":request.blocked_actions,"warning_codes":(),"risk_codes":()}
        grant=build_local_authorization_grant(pre, mat, op_ev, pol_ev, authorization_domain=request.requested_authorization_domain, grant_scope=request.requested_scope, grant_id=plan.intended_grant_id, created_at=self.clock())
        if grant.live_authorization_granted is not True or validate_local_authorization_grant(grant).ok is not True: raise ValueError("grant_validation_failed")
        expiry=build_local_authorization_grant_expiry_evaluation(grant, evaluated_at=self.clock())
        verification=verify_local_authorization_grant(grant, checked_scope_labels=grant.granted_scope_labels, checked_time_label=self.clock(), expiry_evaluation=expiry)
        ledger=build_local_authorization_grant_ledger((grant,), (), (expiry,), created_at=self.clock())
        receipt0=HostLocalAuthorizationIssueReceipt(SCHEMA_VERSION,_id("hlair_", {"plan":plan.digest,"grant":grant.digest}),"","issued",request.request_id,request.digest,plan.plan_id,plan.digest,admission.admission_decision_ref,admission.outcome.value,grant.grant_id,grant.digest,ledger.ledger_id,ledger.digest,plan.idempotency_key,plan.attempt_id,self.clock(),False,True)
        receipt=replace(receipt0,digest=_digest_record(receipt0.to_dict()))
        snap=self._snapshot(ledger,(receipt,),())
        docs={"review_request.json":request.to_dict(),"operator_decision.json":operator.to_dict(),"policy_decision.json":policy.to_dict(),"issue_plan.json":plan.to_dict(),"admission.json":admission.to_dict(),"grant_record.json":grant.to_dict(),"issue_receipt.json":receipt.to_dict(),"expiry_evaluation.json":expiry.to_dict(),"verification.json":verification.to_dict(),"ledger_snapshot.json":snap.to_dict(),"summary.json":summarize_snapshot(snap),"README.md":render_markdown(snap)}
        tmp=root/(".tmp_"+receipt.receipt_id); tmp.mkdir(parents=True, exist_ok=True)
        for name,payload in docs.items(): (tmp/name).write_text(payload if isinstance(payload,str) else json.dumps(payload,sort_keys=True,indent=2), encoding="utf-8")
        for p in tmp.iterdir(): p.replace(root/p.name)
        tmp.rmdir()
        index[plan.idempotency_key]={"semantic":sem,"receipt":receipt.to_dict()}; index_path.write_text(json.dumps(index,sort_keys=True,indent=2),encoding="utf-8")
        (root/"latest.json").write_text(json.dumps({"request_id":request.request_id,"grant_id":grant.grant_id,"receipt_id":receipt.receipt_id,"ledger_id":ledger.ledger_id},sort_keys=True,indent=2),encoding="utf-8")
        return receipt
    def _snapshot(self, ledger: LocalAuthorizationGrantLedger, issues: Sequence[HostLocalAuthorizationIssueReceipt], revs: Sequence[HostLocalAuthorizationRevocationReceipt]) -> HostLocalAuthorizationLedgerSnapshot:
        snap0=HostLocalAuthorizationLedgerSnapshot(SCHEMA_VERSION,_id("hlas_", {"ledger":ledger.digest,"issues":[r.digest for r in issues],"revs":[r.digest for r in revs]}),"",ledger,tuple(issues),tuple(revs),ledger.active_grant_count,ledger.expired_grant_count,ledger.revoked_grant_count,0,self.clock())
        return replace(snap0,digest=_digest_record(snap0.to_dict()))
    def evaluate_expiry(self, grant: LocalAuthorizationGrant, *, now: str|None=None) -> LocalAuthorizationGrantExpiryEvaluation: return build_local_authorization_grant_expiry_evaluation(grant, evaluated_at=now or self.clock())
    def revoke(self, grant: LocalAuthorizationGrant, decision: HostLocalAuthorizationRevocationDecision, ledger: LocalAuthorizationGrantLedger, *, apply: bool=False) -> HostLocalAuthorizationRevocationReceipt:
        self.revoke_call_count += 1
        if not apply: raise RuntimeError("not_applied")
        if decision.grant_id != grant.grant_id or decision.grant_digest != grant.digest or decision.current_ledger_digest != ledger.digest: raise ValueError("revocation_binding_mismatch")
        local=build_local_authorization_grant_revocation_receipt(grant, revocation_reason_codes=decision.reason_codes, created_at=self.clock())
        grants=tuple(g if isinstance(g, LocalAuthorizationGrant) else LocalAuthorizationGrant(**g) for g in ledger.grant_records)
        revs=tuple(ledger.revocation_receipts) + (local,)
        exps=tuple(e if isinstance(e, LocalAuthorizationGrantExpiryEvaluation) else LocalAuthorizationGrantExpiryEvaluation(**e) for e in ledger.expiry_evaluations)
        new_ledger=build_local_authorization_grant_ledger(grants, revs, exps, created_at=self.clock())
        rec0=HostLocalAuthorizationRevocationReceipt(SCHEMA_VERSION,_id("hlarr_", {"decision":decision.digest,"grant":grant.digest}),"","revoked",decision.decision_id,decision.digest,grant.grant_id,grant.digest,new_ledger.ledger_id,new_ledger.digest,local.receipt_id,local.digest,self.clock())
        return replace(rec0,digest=_digest_record(rec0.to_dict()))

def build_revocation_decision(grant: LocalAuthorizationGrant, ledger: LocalAuthorizationGrantLedger, *, identity: str, reason_codes: Sequence[str], effective_at: str="immediate", custody_timestamp: str="1970-01-01T00:00:00+00:00") -> HostLocalAuthorizationRevocationDecision:
    sem={"schema_version":SCHEMA_VERSION,"grant_id":grant.grant_id,"grant_digest":grant.digest,"current_ledger_digest":ledger.digest,"identity":identity,"reason_codes":tuple(sorted(reason_codes)),"effective_at":effective_at,"metadata_only":True,"reduces_authority_only":True,"authorizes_fulfillment":False,"effect_performed":False,"host_mutation_performed":False}
    d0=HostLocalAuthorizationRevocationDecision(SCHEMA_VERSION,_id("hlard_", sem),"",grant.grant_id,grant.digest,ledger.digest,identity,tuple(sorted(reason_codes)),effective_at,custody_timestamp)
    return replace(d0,digest=_digest_record(d0.to_dict()))

def summarize_snapshot(snapshot: HostLocalAuthorizationLedgerSnapshot | Mapping[str, Any]) -> dict[str, Any]:
    p=_dict(snapshot); ledger=p.get("ledger", {})
    return {"status":"recorded","active_grant_count":p.get("active_count",0),"expired_grant_count":p.get("expired_count",0),"revoked_grant_count":p.get("revoked_count",0),"conflicted_grant_count":p.get("conflicted_count",0),"latest_ids":[p.get("snapshot_id"), ledger.get("ledger_id") if isinstance(ledger,dict) else None],"read_only":True,"local_authority_metadata_only":True,"fulfillment_granted":False,"execution_triggered":False,"host_mutation_performed":False}

def render_markdown(snapshot: HostLocalAuthorizationLedgerSnapshot | Mapping[str, Any]) -> str:
    s=summarize_snapshot(snapshot)
    return "\n".join(["# Host Local Authorization Grant Custody","",f"- Active grants: `{s['active_grant_count']}`",f"- Expired grants: `{s['expired_grant_count']}`",f"- Revoked grants: `{s['revoked_grant_count']}`","- Authority: local metadata only; no fulfillment, backend execution, privileged host-effect admission, or host mutation.",""])

def world_state_records(*, request: HostLocalAuthorizationReviewRequest|None=None, operator_decision: OperatorLocalAuthorizationDecision|None=None, policy_decision: PolicyLocalAuthorizationDecision|None=None, plan: HostLocalAuthorizationIssuePlan|None=None, issue_receipt: HostLocalAuthorizationIssueReceipt|None=None, snapshot: HostLocalAuthorizationLedgerSnapshot|None=None, revocation_receipt: HostLocalAuthorizationRevocationReceipt|None=None, observed_at: str="1970-01-01T00:00:00+00:00") -> list[dict[str, Any]]:
    records=[]
    for stage, kind, obj in (("review","host_local_authorization_review_request",request),("review","host_local_authorization_operator_decision",operator_decision),("review","host_local_authorization_policy_decision",policy_decision),("admission_candidate","host_local_authorization_issue_plan",plan),("admission","host_local_authorization_issue_receipt",issue_receipt),("admission","host_local_authorization_ledger",snapshot),("rollback","host_local_authorization_revocation",revocation_receipt)):
        if obj is None: continue
        payload={**_dict(obj),"fulfillment_granted":False,"effect_claimed":False,"effect_proven":False,"host_mutation_performed":False}
        sid=payload.get("request_id") or payload.get("decision_id") or payload.get("plan_id") or payload.get("receipt_id") or payload.get("snapshot_id")
        records.append({"source_kind":WorldStateSourceKind.PRIVILEGE.value,"schema_version":SCHEMA_VERSION,"observed_at":observed_at,"required":False,"evidence_strength":"recorded","effect_claimed":False,"effect_proven":False,"source_id":f"hlar:{sid}:{kind}","subject_id":str(sid),"subject_kind":kind,"stage":stage,"disposition":payload.get("issue_status") or payload.get("disposition") or "recorded","payload":payload,"digest":world_digest(payload)})
    return records

def dashboard_projection(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pending=approve=reject=defer=active=expired=revoked=conflicted=0; blocked: set[str]=set(); latest: list[str]=[]; scopes: list[str]=[]; expiries: list[str]=[]; admission="unavailable"
    for rec in records:
        p=rec.get("payload", {}) if isinstance(rec.get("payload"), Mapping) else {}
        k=rec.get("subject_kind", "")
        latest.append(str(rec.get("subject_id","")))
        blocked.update(str(x) for x in p.get("blocked_actions", ()) or ())
        if k == "host_local_authorization_review_request": pending += 1; scopes.append(str(p.get("requested_scope",""))); expiries.append(str(p.get("expiry","")))
        if p.get("disposition") == "approve": approve += 1
        if p.get("disposition") == "reject": reject += 1
        if p.get("disposition") == "defer": defer += 1
        if p.get("issue_status") == "issued": admission="allowed"
        active += int(p.get("active_count",0) or 0); expired += int(p.get("expired_count",0) or 0); revoked += int(p.get("revoked_count",0) or 0); conflicted += int(p.get("conflicted_count",0) or 0)
    return {"status":"recorded" if records else "unavailable","pending_review_request_count":pending,"decision_counts":{"approve":approve,"reject":reject,"defer":defer},"issuance_admission_posture":admission,"grant_counts":{"active":active,"expired":expired,"revoked":revoked,"conflicted":conflicted},"scope_summaries":sorted(set(scopes)),"expiry_summaries":sorted(set(expiries)),"blocked_actions":sorted(blocked),"latest_ids":[x for x in latest[-20:] if x],"read_only":True,"local_authority_metadata_only":True,"fulfillment_granted":False,"execution_triggered":False,"host_mutation_performed":False}
