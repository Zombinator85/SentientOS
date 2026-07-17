# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type,union-attr,var-annotated"
"""Same-tick controlled authorization and host-actuation safety runtime closure.

Consumes an in-memory HostExecutionReadinessEvaluation and builds only
metadata/review records. It never issues live grants, privileged-effect
admission, fulfillment, backend invocation, host effects, or repository mutation.
"""
from __future__ import annotations

import hashlib, json, os, tempfile
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sentientos.control_plane_kernel import AuthorityClass, ControlActionDecision, ControlActionRequest, ControlPlaneKernel, LifecyclePhase, get_control_plane_kernel
from sentientos.host_execution_readiness_runtime import HostExecutionReadinessEvaluation, HostExecutionReadinessItem, validate_item_chain
from sentientos.controlled_authorization import (
    build_controlled_authorization_grant_contract, build_controlled_authorization_grant_record,
    build_controlled_authorization_revocation_record, build_controlled_authorization_ledger,
    validate_controlled_authorization_grant_contract, validate_controlled_authorization_grant_record,
    validate_controlled_authorization_revocation_record, validate_controlled_authorization_ledger,
    ControlledAuthorizationWingRecords,
)
from sentientos.host_actuation_safety import (
    build_safety_gates_for_controlled_authorization_contract, build_safety_gate_satisfaction_manifest, validate_safety_gate_satisfaction_manifest,
    validate_host_actuation_gate_assessment, host_actuation_gate_assessment_digest,
    safety_gate_satisfaction_manifest_digest,
)
from sentientos.world_state_board import WorldStateSourceKind, digest

SCHEMA_VERSION = "host_controlled_authorization_safety_runtime.v1"
NON_AUTHORITY = {"live_authorization_granted": False, "fulfillment_granted": False, "effect_claimed": False, "effect_proven": False, "host_mutation_performed": False}

def _canon(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), default=lambda o: asdict(o) if hasattr(o, "__dataclass_fields__") else str(o))
def _sha(v: Any) -> str: return hashlib.sha256(_canon(v).encode()).hexdigest()
def _id(p: str, v: Any) -> str: return p + _sha(v)[:24]
def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _to_dict(v: Any) -> dict[str, Any]: return asdict(v) if hasattr(v, "__dataclass_fields__") else dict(v)

def _stable_created_at(*_args: Any) -> str:
    return "1970-01-01T00:00:00+00:00"

@dataclass(frozen=True)
class HostControlledAuthorizationBudget:
    max_items: int = 32; max_serialized_item_bytes: int = 262144; max_bundle_bytes: int = 2097152; max_bundle_files: int = 32; retry_count: int = 0
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostControlledAuthorizationPlan:
    plan_id: str; semantic_digest: str; budget: HostControlledAuthorizationBudget; authority_class: str = AuthorityClass.PROPOSAL_EVALUATION.value; metadata_only: bool = True; review_only: bool = True; no_effect_authority: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostControlledAuthorizationSourceRef:
    source_execution_readiness_evaluation_id: str; source_execution_readiness_evaluation_digest: str; source_execution_readiness_manifest_id: str; source_execution_readiness_manifest_digest: str; authorization_review_packet_id: str; authorization_review_packet_digest: str; authorization_review_decision_id: str; authorization_review_decision_digest: str; authorization_review_receipt_id: str; authorization_review_receipt_digest: str; future_authorization_schema_id: str; future_authorization_schema_digest: str; source_tick_id: str; correlation_id: str; authorization_domain: str; approval_class: str; blocked_actions: tuple[str, ...]; required_future_gates: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostControlledAuthorizationItem:
    item_id: str; source_ref: HostControlledAuthorizationSourceRef | None; valid_source: bool; findings: tuple[str, ...]; controlled_authorization: ControlledAuthorizationWingRecords | None = None; safety_bundle: Any | None = None
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostControlledAuthorizationRuntimeSummary:
    status: str; evaluation_id: str; chain_id: str; source_chain_count: int; valid_item_count: int; invalid_item_count: int; contract_status_counts: Mapping[str, int]; schema_grant_posture_counts: Mapping[str, int]; safety_gate_status_counts: Mapping[str, int]; missing_gates: tuple[str, ...]; blocked_actions: tuple[str, ...]; findings: tuple[str, ...]; read_only: bool = True; review_only: bool = True; live_authorization_granted: bool = False; fulfillment_granted: bool = False; execution_triggered: bool = False; host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostControlledAuthorizationEvaluation:
    evaluation_id: str; chain_id: str; plan: HostControlledAuthorizationPlan; admission_ref: Mapping[str, Any]; source_execution_readiness_evaluation_id: str; source_execution_readiness_evaluation_digest: str; source_tick_id: str; correlation_id: str; items: tuple[HostControlledAuthorizationItem, ...]; validation_findings: tuple[str, ...]; summary: HostControlledAuthorizationRuntimeSummary; semantic_digest: str; observed_at: str; no_authority: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostControlledAuthorizationReceipt:
    receipt_id: str; evaluation_id: str; bundle_digest: str; artifact_root: str; artifact_paths: Mapping[str, str]; semantic_digest: str; repository_mutation_performed: bool = False; host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostControlledAuthorizationRuntimeValidationResult:
    ok: bool; findings: tuple[str, ...] = ()

def build_host_controlled_authorization_plan(budget: HostControlledAuthorizationBudget | None = None) -> HostControlledAuthorizationPlan:
    b = budget or HostControlledAuthorizationBudget(); sem = {"schema": SCHEMA_VERSION, "budget": b.to_dict(), "authority": AuthorityClass.PROPOSAL_EVALUATION.value, "metadata_only": True}
    return HostControlledAuthorizationPlan(_id("hcap_", sem), _sha(sem), b)

def _source_ref(evaluation: HostExecutionReadinessEvaluation, item: HostExecutionReadinessItem) -> tuple[HostControlledAuthorizationSourceRef | None, tuple[str, ...]]:
    findings = list(validate_item_chain(item).findings)
    m, p, d, r, s = item.execution_readiness_manifest, item.authorization_review_packet, item.authorization_review_decision, item.authorization_review_receipt, item.future_authorization_grant_schema
    if not item.valid_source or any(x is None for x in (m, p, d, r, s)): findings.append("missing_or_invalid_execution_readiness_review_chain")
    if findings: return None, tuple(sorted(set(findings)))
    assert m is not None and p is not None and d is not None and r is not None and s is not None
    if s.source_authorization_review_receipt_id != r.receipt_id or s.source_authorization_review_receipt_digest != r.digest: findings.append("review_receipt_future_schema_mismatch")
    if p.source_execution_readiness_manifest_id != m.manifest_id: findings.append("source_manifest_mismatch")
    if getattr(r, "authorization_not_granted", True) is not True or getattr(s, "authorization_granted", False): findings.append("source_claims_live_authorization")
    if getattr(m, "effect_performed", False) or getattr(m, "host_mutation_performed", False): findings.append("source_claims_effect_or_host_mutation")
    if findings: return None, tuple(sorted(set(findings)))
    return HostControlledAuthorizationSourceRef(evaluation.evaluation_id, evaluation.semantic_digest, m.manifest_id, getattr(m, "digest", _sha(_to_dict(m))), p.packet_id, getattr(p, "source_execution_readiness_manifest_digest", _sha(_to_dict(p))), d.decision_id, _sha(_to_dict(d)), r.receipt_id, r.digest, s.schema_id, s.digest, evaluation.source_tick_id, evaluation.correlation_id, r.authorization_domain, r.approval_class, tuple(sorted(r.blocked_actions)), tuple(sorted(getattr(s, "required_future_gates", getattr(s, "required_grant_gates", ())) or ()))), ()

def validate_evaluation(evaluation: HostControlledAuthorizationEvaluation) -> HostControlledAuthorizationRuntimeValidationResult:
    findings = list(evaluation.validation_findings)
    if not evaluation.no_authority: findings.append("authority_flag_true")
    for it in evaluation.items:
        if not it.valid_source: findings.extend(f"{it.item_id}:{f}" for f in it.findings); continue
        if it.controlled_authorization is None or it.safety_bundle is None: findings.append(f"{it.item_id}:missing_downstream_records"); continue
        ca = it.controlled_authorization
        for prefix, result in (("contract", validate_controlled_authorization_grant_contract(ca.contract)), ("grant_record", validate_controlled_authorization_grant_record(ca.grant_record)), ("revocation", validate_controlled_authorization_revocation_record(ca.revocation_record)), ("ledger", validate_controlled_authorization_ledger(ca.ledger))):
            findings.extend(f"{it.item_id}:{prefix}:{f}" for f in result.findings)
        if ca.grant_record.contract_id != ca.contract.contract_id or ca.revocation_record.grant_record_id != ca.grant_record.grant_record_id: findings.append(f"{it.item_id}:controlled_authorization_linkage_mismatch")
        sb = it.safety_bundle
        for a in sb.gate_assessments: findings.extend(f"{it.item_id}:safety_assessment:{f}" for f in validate_host_actuation_gate_assessment(a).findings)
        findings.extend(f"{it.item_id}:safety_manifest:{f}" for f in validate_safety_gate_satisfaction_manifest(sb.safety_gate_satisfaction_manifest).findings)
        if sb.safety_gate_satisfaction_manifest.source_controlled_authorization_contract_id != ca.contract.contract_id: findings.append(f"{it.item_id}:safety_contract_linkage_mismatch")
    return HostControlledAuthorizationRuntimeValidationResult(not findings, tuple(sorted(set(findings))))

def _summary(eid: str, cid: str, items: Sequence[HostControlledAuthorizationItem], findings: Sequence[str]) -> HostControlledAuthorizationRuntimeSummary:
    contracts: dict[str,int] = {}; grants: dict[str,int] = {}; gates: dict[str,int] = {}; missing: set[str] = set(); blocked: set[str] = set()
    for it in items:
        ca, sb = it.controlled_authorization, it.safety_bundle
        if ca: contracts[ca.contract.status] = contracts.get(ca.contract.status,0)+1; grants[ca.grant_record.grant_status] = grants.get(ca.grant_record.grant_status,0)+1; blocked.update(ca.contract.blocked_actions)
        if sb:
            man = sb.safety_gate_satisfaction_manifest; missing.update(man.missing_gate_labels); blocked.update(man.blocked_actions)
            for a in sb.gate_assessments: gates[a.gate_status] = gates.get(a.gate_status,0)+1
    valid=sum(1 for i in items if i.valid_source)
    return HostControlledAuthorizationRuntimeSummary("degraded" if findings or valid != len(items) else "ok", eid, cid, len(items), valid, len(items)-valid, contracts, grants, gates, tuple(sorted(missing)), tuple(sorted(blocked)), tuple(sorted(set(findings))))

class HostControlledAuthorizationRuntimeCoordinator:
    def __init__(self, *, kernel: ControlPlaneKernel | None = None, runtime_state_root: Path | str | None = None, plan: HostControlledAuthorizationPlan | None = None, clock: Callable[[], str] | None = None) -> None:
        self.kernel = kernel or get_control_plane_kernel(); self.runtime_state_root = Path(runtime_state_root or os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT") or (tempfile.gettempdir()+"/sentientos_runtime")); self.plan = plan or build_host_controlled_authorization_plan(); self.clock = clock or _now; self._by_correlation: dict[str, HostControlledAuthorizationEvaluation] = {}; self._tick_seen: set[str] = set(); self.builder_call_count = 0
    def request_admission(self, *, tick_id: str, correlation_id: str, source_evaluation: HostExecutionReadinessEvaluation, first_ref: HostControlledAuthorizationSourceRef) -> ControlActionDecision:
        return self.kernel.admit(ControlActionRequest("host_controlled_authorization_safety_runtime", AuthorityClass.PROPOSAL_EVALUATION, "sentientosd", "host_controlled_authorization_safety_runtime", LifecyclePhase.MAINTENANCE, {"correlation_id": correlation_id, "common_correlation_id": source_evaluation.correlation_id, "tick_id": tick_id, "source_execution_readiness_evaluation_id": source_evaluation.evaluation_id, "source_execution_readiness_evaluation_digest": source_evaluation.semantic_digest, "authorization_review_receipt_id": first_ref.authorization_review_receipt_id, "authorization_review_receipt_digest": first_ref.authorization_review_receipt_digest, "future_authorization_schema_id": first_ref.future_authorization_schema_id, "future_authorization_schema_digest": first_ref.future_authorization_schema_digest, "runtime_plan_id": self.plan.plan_id, "runtime_plan_digest": self.plan.semantic_digest, "metadata_only": True, "grants_live_authorization": False, "grants_privileged_effect_admission": False, "grants_fulfillment": False}))
    def run_cycle(self, *, tick_id: str, source_evaluation: HostExecutionReadinessEvaluation | None, correlation_id: str | None = None, decision: ControlActionDecision | None = None, persist: bool = True) -> HostControlledAuthorizationEvaluation | None:
        corr = correlation_id or f"{tick_id}:host_controlled_authorization_safety_runtime"
        if corr in self._by_correlation: return self._by_correlation[corr]
        if tick_id in self._tick_seen or source_evaluation is None or getattr(source_evaluation, "no_authority", False) is not True: return None
        refs = [_source_ref(source_evaluation, i) for i in sorted(source_evaluation.items, key=lambda x: x.item_id)[:self.plan.budget.max_items]]
        valid_refs = [r for r, f in refs if r is not None and not f]
        if not valid_refs: return None
        decision = decision or self.request_admission(tick_id=tick_id, correlation_id=corr, source_evaluation=source_evaluation, first_ref=valid_refs[0])
        if not getattr(decision, "allowed", False): return None
        items=[]; seen: dict[str,str] = {}
        by_item = dict(zip(sorted(source_evaluation.items, key=lambda x: x.item_id)[:self.plan.budget.max_items], refs))
        for src, (ref, findings) in by_item.items():
            local_findings=list(findings)
            if ref and ref.authorization_review_receipt_id in seen and seen[ref.authorization_review_receipt_id] != ref.authorization_review_receipt_digest: local_findings.append("duplicate_semantic_id_conflicting_digest")
            if ref: seen[ref.authorization_review_receipt_id]=ref.authorization_review_receipt_digest
            if local_findings or ref is None:
                items.append(HostControlledAuthorizationItem(_id("hcai_", (getattr(src,"item_id","unknown"), local_findings)), ref, False, tuple(sorted(set(local_findings))))); continue
            assert src.authorization_review_receipt is not None and src.future_authorization_grant_schema is not None
            c = build_controlled_authorization_grant_contract(src.authorization_review_receipt, src.future_authorization_grant_schema, created_at=_stable_created_at())
            g = build_controlled_authorization_grant_record(c, created_at=_stable_created_at())
            rv = build_controlled_authorization_revocation_record(g, created_at=_stable_created_at())
            led = build_controlled_authorization_ledger((g,), (rv,), created_at=_stable_created_at())
            sb = build_safety_gates_for_controlled_authorization_contract(c, created_at=_stable_created_at())
            forced_missing = {"control_plane_admission_required", "effect_receipt_required", "rollback_receipt_required", "postcondition_check_required"}
            assessments = tuple(
                replace(a, gate_status="host_actuation_gate_missing", evidence_labels=(), missing_labels=(a.gate_label,))
                if a.gate_label in forced_missing else a
                for a in sb.gate_assessments
            )
            man = build_safety_gate_satisfaction_manifest(
                sb.safety_gate_satisfaction_manifest.domain,
                hardware_allowlist_manifest=sb.hardware_allowlist_manifest,
                os_backend_declaration=sb.os_backend_declaration,
                bounds_policy=sb.bounds_policy,
                cooldown_policy=sb.cooldown_policy,
                panic_stop_contract=sb.panic_stop_contract,
                host_action_scope_manifest=sb.host_action_scope_manifest,
                gate_assessments=assessments,
                source_controlled_authorization_contract_id=c.contract_id,
                source_controlled_authorization_contract_digest=c.digest,
                created_at=_stable_created_at(),
            )
            sb = replace(sb, gate_assessments=assessments, safety_gate_satisfaction_manifest=man)
            self.builder_call_count += 5
            item = HostControlledAuthorizationItem(_id("hcai_", (ref.to_dict(), c.contract_id, g.grant_record_id, sb.safety_gate_satisfaction_manifest.manifest_id)), ref, True, (), ControlledAuthorizationWingRecords(c,g,rv,led), sb)
            if len(_canon(item.to_dict()).encode()) > self.plan.budget.max_serialized_item_bytes:
                item = HostControlledAuthorizationItem(item.item_id, ref, False, ("serialized_item_exceeds_budget",), item.controlled_authorization, item.safety_bundle)
            items.append(item)
        sem={"schema": SCHEMA_VERSION, "plan": self.plan.semantic_digest, "source": source_evaluation.evaluation_id, "source_digest": source_evaluation.semantic_digest, "items": [i.item_id for i in items], "correlation_id": corr}
        eid=_id("hcae_", sem); cid=_id("hcac_", sem)
        adm={"admission_decision_ref": decision.admission_decision_ref, "outcome": decision.outcome.value, "authority_class": decision.authority_class.value, "action_kind": decision.action_kind, "correlation_id": decision.correlation_id, "grants_live_authorization": False, "grants_privileged_effect_admission": False, "grants_fulfillment": False, "grants_execution": False}
        ev=HostControlledAuthorizationEvaluation(eid,cid,self.plan,adm,source_evaluation.evaluation_id,source_evaluation.semantic_digest,tick_id,corr,tuple(items),(),_summary(eid,cid,items,()),_sha(sem),self.clock(),True)
        val=validate_evaluation(ev)
        if not val.ok: ev=HostControlledAuthorizationEvaluation(eid,cid,self.plan,adm,source_evaluation.evaluation_id,source_evaluation.semantic_digest,tick_id,corr,tuple(items),val.findings,_summary(eid,cid,items,val.findings),_sha(sem),ev.observed_at,True)
        self._by_correlation[corr]=ev; self._tick_seen.add(tick_id)
        if persist: persist_evidence_bundle(self.runtime_state_root, ev, tick_id=tick_id)
        return ev

def _safe_root(root: Path | str) -> Path:
    r=Path(root).resolve(); r.mkdir(parents=True, exist_ok=True)
    if r.is_symlink() or any(part == ".." for part in r.parts): raise ValueError("unsafe_runtime_state_root")
    return r

def render_markdown(evaluation: HostControlledAuthorizationEvaluation) -> str:
    return "\n".join(["# Host Controlled Authorization Safety Runtime", "", f"- Evaluation: `{evaluation.evaluation_id}`", f"- Chain: `{evaluation.chain_id}`", f"- Source execution readiness: `{evaluation.source_execution_readiness_evaluation_id}`", f"- Valid/invalid items: `{evaluation.summary.valid_item_count}/{evaluation.summary.invalid_item_count}`", "- Authority: review only; no live grant, fulfillment, privileged-effect admission, execution, or host mutation.", ""])

def persist_evidence_bundle(root: Path | str, evaluation: HostControlledAuthorizationEvaluation, *, tick_id: str) -> HostControlledAuthorizationReceipt:
    base=_safe_root(root)/"host_controlled_authorization_runtime"/_id("tick_", {"tick":tick_id,"evaluation":evaluation.evaluation_id}); base.mkdir(parents=True, exist_ok=True)
    contracts=[]; grants=[]; revs=[]; ledgers=[]; safety=[]; assessments=[]; manifests=[]
    for it in evaluation.items:
        if it.controlled_authorization:
            contracts.append(_to_dict(it.controlled_authorization.contract)); grants.append(_to_dict(it.controlled_authorization.grant_record)); revs.append(_to_dict(it.controlled_authorization.revocation_record)); ledgers.append(_to_dict(it.controlled_authorization.ledger))
        if it.safety_bundle:
            safety.append({"domain": it.safety_bundle.safety_gate_satisfaction_manifest.domain, "hardware_allowlist_manifest": _to_dict(it.safety_bundle.hardware_allowlist_manifest) if it.safety_bundle.hardware_allowlist_manifest else None, "os_backend_declaration": _to_dict(it.safety_bundle.os_backend_declaration) if it.safety_bundle.os_backend_declaration else None, "bounds_policy": _to_dict(it.safety_bundle.bounds_policy) if it.safety_bundle.bounds_policy else None, "cooldown_policy": _to_dict(it.safety_bundle.cooldown_policy) if it.safety_bundle.cooldown_policy else None, "panic_stop_contract": _to_dict(it.safety_bundle.panic_stop_contract) if it.safety_bundle.panic_stop_contract else None, "host_action_scope_manifest": _to_dict(it.safety_bundle.host_action_scope_manifest) if it.safety_bundle.host_action_scope_manifest else None})
            assessments.extend(_to_dict(a) for a in it.safety_bundle.gate_assessments); manifests.append(_to_dict(it.safety_bundle.safety_gate_satisfaction_manifest))
    objs={"runtime_plan": evaluation.plan.to_dict(), "admission_reference": dict(evaluation.admission_ref), "source_evidence_manifest": {"evaluation_id": evaluation.source_execution_readiness_evaluation_id, "digest": evaluation.source_execution_readiness_evaluation_digest}, "controlled_authorization_contracts": contracts, "schema_grant_records": grants, "revocation_schemas": revs, "authorization_ledgers": ledgers, "typed_safety_evidence_manifests": safety, "safety_gate_assessments": assessments, "safety_gate_satisfaction_manifests": manifests, "validation_findings": list(evaluation.validation_findings), "summary": evaluation.summary.to_dict(), "items": [i.to_dict() for i in evaluation.items]}
    total=0; paths={}
    for name,obj in objs.items():
        data=json.dumps(obj, sort_keys=True, indent=2, default=str).encode(); total += len(data)
        if total > evaluation.plan.budget.max_bundle_bytes: raise ValueError("bundle_size_exceeds_budget")
        target=base/f"{name}.json"; tmp=target.with_suffix(".json.tmp"); tmp.write_bytes(data); tmp.replace(target); paths[name]=target.as_posix()
    md=base/"summary.md"; tmp=md.with_suffix(".md.tmp"); tmp.write_text(render_markdown(evaluation), encoding="utf-8"); tmp.replace(md); paths["markdown"]=md.as_posix()
    bdig=digest(objs); latest=base.parent/"latest.json"; lp={"evaluation_id": evaluation.evaluation_id, "chain_id": evaluation.chain_id, "bundle_digest": bdig, "status": evaluation.summary.status, "read_only": True, "review_only": True, "live_authorization_granted": False, "fulfillment_granted": False, "execution_triggered": False, "host_mutation_performed": False}; tmp=latest.with_suffix(".json.tmp"); tmp.write_text(json.dumps(lp, sort_keys=True, indent=2), encoding="utf-8"); tmp.replace(latest)
    return HostControlledAuthorizationReceipt(_id("hcar_", {"evaluation": evaluation.evaluation_id, "bundle": bdig}), evaluation.evaluation_id, bdig, base.as_posix(), paths, evaluation.semantic_digest)

def world_state_records(evaluation: HostControlledAuthorizationEvaluation) -> list[dict[str, Any]]:
    out=[]; base={"source_kind": WorldStateSourceKind.FULFILLMENT.value, "schema_version": SCHEMA_VERSION, "observed_at": evaluation.observed_at, **NON_AUTHORITY}
    for it in evaluation.items:
        if not it.valid_source: continue
        ca, sb = it.controlled_authorization, it.safety_bundle
        if ca:
            for kind,obj,disp,dig in (("controlled_authorization_contract", ca.contract, ca.contract.status, ca.contract.digest), ("controlled_authorization_schema_grant_record", ca.grant_record, ca.grant_record.grant_status, ca.grant_record.digest), ("controlled_authorization_revocation_schema", ca.revocation_record, ca.revocation_record.revocation_status, ca.revocation_record.digest), ("controlled_authorization_ledger", ca.ledger, ca.ledger.ledger_status, ca.ledger.digest)):
                payload={"source_lineage": it.source_ref.to_dict() if it.source_ref else {}, "status": disp, "blocked_actions": tuple(getattr(obj,"blocked_actions",()) or ()), "live_authorization_granted": False, "fulfillment_granted": False, "effect_claimed": False, "effect_proven": False, "host_mutation_performed": False}
                out.append({**base,"source_id":f"hca:{getattr(obj,'contract_id',getattr(obj,'grant_record_id',getattr(obj,'revocation_id',getattr(obj,'ledger_id','unknown'))))}","subject_id":getattr(obj,'contract_id',getattr(obj,'grant_record_id',getattr(obj,'revocation_id',getattr(obj,'ledger_id','unknown')))),"subject_kind":f"host_{kind}","stage":"review","disposition":disp,"payload":payload,"digest":dig})
        if sb:
            man=sb.safety_gate_satisfaction_manifest
            for a in sb.gate_assessments:
                payload={"source_lineage": it.source_ref.to_dict() if it.source_ref else {}, "status": a.gate_status, "satisfied_gates": (a.gate_label,) if "satisfied" in a.gate_status else (), "missing_gates": a.missing_labels, "blocked_actions": a.blocked_actions, "live_authorization_granted": False, "fulfillment_granted": False, "effect_claimed": False, "effect_proven": False, "host_mutation_performed": False}
                out.append({**base,"source_id":f"hca:{a.assessment_id}","subject_id":a.assessment_id,"subject_kind":"host_actuation_safety_gate_assessment","stage":"review","disposition":a.gate_status,"payload":payload,"digest":host_actuation_gate_assessment_digest(a)})
            payload={"source_lineage": it.source_ref.to_dict() if it.source_ref else {}, "status": man.safety_status, "satisfied_gates": man.satisfied_gate_labels, "missing_gates": man.missing_gate_labels, "blocked_actions": man.blocked_actions, "live_authorization_granted": False, "fulfillment_granted": False, "effect_claimed": False, "effect_proven": False, "host_mutation_performed": False}
            out.append({**base,"source_id":f"hca:{man.manifest_id}","subject_id":man.manifest_id,"subject_kind":"host_actuation_safety_satisfaction_manifest","stage":"review","disposition":man.safety_status,"payload":payload,"digest":safety_gate_satisfaction_manifest_digest(man)})
    return out

def summary_for_evaluation(evaluation: HostControlledAuthorizationEvaluation) -> dict[str, Any]: return evaluation.summary.to_dict()
