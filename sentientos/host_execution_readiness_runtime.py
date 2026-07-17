# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type,union-attr"
"""Same-tick execution-readiness and authorization-review runtime closure.

Evidence-only coordinator: consumes an in-memory HostPrivilegeReviewEvaluation and
its exact fulfillment rehearsal receipts, obtains proposal-evaluation admission,
builds proof/review records, persists bounded external artifacts, and projects
World-State records. It never grants authorization, invokes controlled
authorization, executes a backend, collects host telemetry, or mutates the host.
"""
from __future__ import annotations

import hashlib, json, os, tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sentientos.authorization_review import (
    build_authorization_review_packet, build_authorization_review_receipt,
    build_future_authorization_grant_schema, evaluate_authorization_review,
    validate_authorization_review_decision, validate_authorization_review_packet,
    validate_authorization_review_receipt, validate_future_authorization_grant_schema,
)
from sentientos.control_plane_kernel import AuthorityClass, ControlActionDecision, ControlActionRequest, ControlPlaneKernel, LifecyclePhase, get_control_plane_kernel
from sentientos.effect_proof import (
    build_effect_receipt_contract, build_execution_readiness_manifest,
    build_future_effect_receipt_schema, build_postcondition_check_plan,
    build_rollback_plan, effect_receipt_contract_digest,
    execution_readiness_manifest_digest, future_effect_receipt_digest,
    postcondition_check_plan_digest, rollback_plan_digest,
    validate_effect_receipt_contract, validate_execution_readiness_manifest,
    validate_future_effect_receipt_schema, validate_postcondition_check_plan,
    validate_rollback_plan,
)
from sentientos.host_privilege_review_runtime import HostPrivilegeReviewEvaluation, HostPrivilegeReviewItem
from sentientos.world_state_board import WorldStateSourceKind, digest

SCHEMA_VERSION = "host_execution_readiness_authorization_review_runtime.v1"
NON_AUTHORITY = {
    "effect_claimed": False, "effect_proven": False, "authorization_granted": False,
    "admission_granted": False, "fulfillment_granted": False, "host_mutation_performed": False,
}

def _canon(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), default=lambda o: asdict(o) if hasattr(o, "__dataclass_fields__") else str(o))
def _id(prefix: str, v: Any) -> str: return prefix + hashlib.sha256(_canon(v).encode()).hexdigest()[:24]
def _sha(v: Any) -> str: return hashlib.sha256(_canon(v).encode()).hexdigest()
def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _to_dict(v: Any) -> dict[str, Any]: return asdict(v) if hasattr(v, "__dataclass_fields__") else dict(v)

@dataclass(frozen=True)
class HostExecutionReadinessBudget:
    max_items: int = 32; max_serialized_item_bytes: int = 262144; max_bundle_bytes: int = 2097152; max_bundle_files: int = 32; retry_count: int = 0
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostExecutionReadinessPlan:
    plan_id: str; semantic_digest: str; budget: HostExecutionReadinessBudget; authority_class: str = AuthorityClass.PROPOSAL_EVALUATION.value; evidence_only: bool = True; no_effect_authority: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostExecutionReadinessSourceRef:
    source_evaluation_id: str; source_evaluation_digest: str; source_item_id: str; source_item_digest: str; host_proposal_receipt_id: str; host_proposal_receipt_digest: str; broker_decision_id: str; broker_decision_digest: str; broker_review_receipt_id: str; broker_review_receipt_digest: str; fulfillment_plan_id: str; fulfillment_plan_digest: str; fulfillment_rehearsal_receipt_id: str; fulfillment_rehearsal_receipt_digest: str; source_tick_id: str; correlation_id: str; rehearsal_status: str; fulfillment_domain: str; backend_class: str; required_future_gates: tuple[str, ...]; blocked_actions: tuple[str, ...]; expected_postconditions: tuple[str, ...]; rollback_requirements: tuple[str, ...]; warning_codes: tuple[str, ...]; risk_codes: tuple[str, ...]; no_effect_posture: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostExecutionReadinessItem:
    item_id: str; source_ref: HostExecutionReadinessSourceRef | None; valid_source: bool; findings: tuple[str, ...]; effect_receipt_contract: Any | None = None; future_effect_receipt_schema: Any | None = None; postcondition_check_plan: Any | None = None; rollback_plan: Any | None = None; execution_readiness_manifest: Any | None = None; authorization_review_packet: Any | None = None; authorization_review_decision: Any | None = None; authorization_review_receipt: Any | None = None; future_authorization_grant_schema: Any | None = None
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostExecutionReadinessRuntimeSummary:
    status: str; evaluation_id: str; chain_id: str; source_rehearsal_count: int; valid_item_count: int; invalid_item_count: int; readiness_status_counts: Mapping[str, int]; authorization_review_status_counts: Mapping[str, int]; findings: tuple[str, ...]; read_only: bool = True; review_only: bool = True; authorization_granted: bool = False; execution_triggered: bool = False; host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostExecutionReadinessEvaluation:
    evaluation_id: str; chain_id: str; plan: HostExecutionReadinessPlan; admission_ref: Mapping[str, Any]; source_privilege_review_evaluation_id: str; source_privilege_review_evaluation_digest: str; source_rehearsal_manifest_digest: str; source_tick_id: str; correlation_id: str; items: tuple[HostExecutionReadinessItem, ...]; validation_findings: tuple[str, ...]; summary: HostExecutionReadinessRuntimeSummary; semantic_digest: str; observed_at: str; no_authority: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostExecutionReadinessRuntimeReceipt:
    receipt_id: str; evaluation_id: str; bundle_digest: str; artifact_root: str; artifact_paths: Mapping[str, str]; semantic_digest: str; repository_mutation_performed: bool = False; host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostExecutionReadinessRuntimeValidationResult:
    ok: bool; findings: tuple[str, ...] = ()

def build_host_execution_readiness_plan(budget: HostExecutionReadinessBudget | None = None) -> HostExecutionReadinessPlan:
    b = budget or HostExecutionReadinessBudget(); sem = {"schema": SCHEMA_VERSION, "budget": b.to_dict(), "authority": AuthorityClass.PROPOSAL_EVALUATION.value, "evidence_only": True}
    return HostExecutionReadinessPlan(_id("herp_", sem), _sha(sem), b)

def _digest_obj(v: Any, fallback: str = "") -> str:
    return str(getattr(v, "digest", "") or fallback or _sha(_to_dict(v)))

def rehearsal_manifest_digest(evaluation: HostPrivilegeReviewEvaluation) -> str:
    rows = []
    for item in sorted(evaluation.items, key=lambda i: (i.source_receipt_id, i.item_id)):
        rr = item.fulfillment_rehearsal_receipt
        if rr is not None: rows.append({"receipt_id": rr.receipt_id, "digest": _digest_obj(rr), "item_id": item.item_id})
    return _sha({"schema": SCHEMA_VERSION, "source": evaluation.evaluation_id, "rows": rows})

def _source_ref(evaluation: HostPrivilegeReviewEvaluation, item: HostPrivilegeReviewItem) -> tuple[HostExecutionReadinessSourceRef | None, tuple[str, ...]]:
    findings: list[str] = []
    bd, br, fp, rr = item.broker_decision, item.broker_review_receipt, item.fulfillment_plan, item.fulfillment_rehearsal_receipt
    if not item.valid_source: findings.extend(item.findings or ("invalid_privilege_review_source",))
    if None in (bd, br, fp, rr): findings.append("missing_rehearsal_chain")
    if findings: return None, tuple(sorted(set(findings)))
    assert bd is not None and br is not None and fp is not None and rr is not None
    if getattr(rr, "effect_performed", False) or not getattr(rr, "does_not_execute", True): findings.append("rehearsal_receipt_claims_execution")
    if getattr(rr, "host_mutation_performed", False) or not getattr(rr, "does_not_mutate_host", True): findings.append("rehearsal_receipt_claims_host_mutation")
    if not getattr(rr, "does_not_authorize_fulfillment", True): findings.append("rehearsal_receipt_claims_authorization")
    if getattr(rr, "source_broker_receipt_digest", "") != getattr(br, "digest", ""): findings.append("rehearsal_broker_receipt_digest_mismatch")
    if getattr(fp, "plan_id", "") != getattr(rr, "plan_id", ""): findings.append("fulfillment_plan_id_mismatch")
    gates = tuple(sorted(str(x) for x in getattr(rr, "required_future_gates", ()) or ()))
    blocked = tuple(sorted(str(x) for x in getattr(rr, "blocked_actions", ()) or ()))
    if any(not x for x in gates): findings.append("malformed_required_gates")
    if any(not x for x in blocked): findings.append("malformed_blocked_actions")
    if findings: return None, tuple(sorted(set(findings)))
    ref = HostExecutionReadinessSourceRef(evaluation.evaluation_id, evaluation.semantic_digest, item.item_id, _sha(item.to_dict()), item.source_receipt_id, item.source_receipt_digest, bd.decision_id, _digest_obj(bd), br.receipt_id, _digest_obj(br), fp.plan_id, _digest_obj(fp), rr.receipt_id, _digest_obj(rr), evaluation.source_tick_id, evaluation.correlation_id, rr.rehearsal_status, rr.fulfillment_domain, rr.backend_class, gates, blocked, tuple(getattr(rr, "expected_postconditions", ()) or ()), tuple(getattr(rr, "rollback_requirements", ()) or ()), tuple(getattr(rr, "warning_codes", ()) or ()), tuple(getattr(rr, "risk_codes", ()) or ()), True)
    return ref, ()

def validate_item_chain(item: HostExecutionReadinessItem) -> HostExecutionReadinessRuntimeValidationResult:
    findings = list(item.findings)
    if not item.valid_source: return HostExecutionReadinessRuntimeValidationResult(False, tuple(sorted(set(findings))))
    objs = (item.effect_receipt_contract, item.future_effect_receipt_schema, item.postcondition_check_plan, item.rollback_plan, item.execution_readiness_manifest, item.authorization_review_packet, item.authorization_review_decision, item.authorization_review_receipt, item.future_authorization_grant_schema)
    if any(o is None for o in objs): findings.append("missing_downstream_record")
    else:
        c, f, p, r, m, ap, ad, ar, ag = objs
        findings += ["contract:"+x for x in validate_effect_receipt_contract(c).findings]
        findings += ["future_schema:"+x for x in validate_future_effect_receipt_schema(f).findings]
        findings += ["postcondition_plan:"+x for x in validate_postcondition_check_plan(p).findings]
        findings += ["rollback_plan:"+x for x in validate_rollback_plan(r).findings]
        findings += ["readiness:"+x for x in validate_execution_readiness_manifest(m).findings]
        findings += ["auth_packet:"+x for x in validate_authorization_review_packet(ap).findings]
        findings += ["auth_decision:"+x for x in validate_authorization_review_decision(ad).findings]
        findings += ["auth_receipt:"+x for x in validate_authorization_review_receipt(ar).findings]
        findings += ["future_grant_schema:"+x for x in validate_future_authorization_grant_schema(ag).findings]
        if c.contract_id != m.effect_contract_id or f.receipt_id != m.future_effect_receipt_id or p.plan_id != m.postcondition_plan_id or r.plan_id != m.rollback_plan_id: findings.append("readiness_nested_ref_mismatch")
        if ap.source_execution_readiness_manifest_id != m.manifest_id or ad.packet_id != ap.packet_id or ar.decision_id != ad.decision_id or ag.source_authorization_review_receipt_id != ar.receipt_id: findings.append("authorization_nested_ref_mismatch")
        if m.authorization_granted or ap.authorization_granted or ad.authorization_granted or ar.authorization_not_granted is not True or ag.authorization_granted: findings.append("authorization_claimed")
        if m.effect_performed or f.effect_performed or c.effect_performed: findings.append("effect_claimed")
    return HostExecutionReadinessRuntimeValidationResult(not findings, tuple(sorted(set(findings))))

def validate_evaluation(evaluation: HostExecutionReadinessEvaluation) -> HostExecutionReadinessRuntimeValidationResult:
    findings = list(evaluation.validation_findings)
    if not evaluation.no_authority: findings.append("authority_flag_true")
    for it in evaluation.items: findings += [f"{it.item_id}:{x}" for x in validate_item_chain(it).findings]
    return HostExecutionReadinessRuntimeValidationResult(not findings, tuple(sorted(set(findings))))

def _summary(eid: str, cid: str, items: tuple[HostExecutionReadinessItem, ...], findings: Sequence[str]) -> HostExecutionReadinessRuntimeSummary:
    ready: dict[str,int] = {}; auth: dict[str,int] = {}
    for it in items:
        if it.execution_readiness_manifest is not None: ready[it.execution_readiness_manifest.readiness_status] = ready.get(it.execution_readiness_manifest.readiness_status,0)+1
        if it.authorization_review_decision is not None: auth[it.authorization_review_decision.decision_status] = auth.get(it.authorization_review_decision.decision_status,0)+1
    valid = sum(1 for i in items if i.valid_source)
    return HostExecutionReadinessRuntimeSummary("degraded" if findings or valid != len(items) else "ok", eid, cid, len(items), valid, len(items)-valid, ready, auth, tuple(sorted(set(findings))))

class HostExecutionReadinessRuntimeCoordinator:
    def __init__(self, *, kernel: ControlPlaneKernel | None = None, runtime_state_root: Path | str | None = None, plan: HostExecutionReadinessPlan | None = None, clock: Callable[[], str] | None = None) -> None:
        self.kernel = kernel or get_control_plane_kernel(); self.runtime_state_root = Path(runtime_state_root or os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT") or (tempfile.gettempdir()+"/sentientos_runtime")); self.plan = plan or build_host_execution_readiness_plan(); self.clock = clock or _now; self._by_correlation: dict[str, HostExecutionReadinessEvaluation] = {}; self._tick_seen: set[str] = set(); self.builder_call_count = 0
    def request_admission(self, *, tick_id: str, correlation_id: str, source_evaluation: HostPrivilegeReviewEvaluation, manifest_digest: str) -> ControlActionDecision:
        return self.kernel.admit(ControlActionRequest("host_execution_readiness_authorization_review_runtime", AuthorityClass.PROPOSAL_EVALUATION, "sentientosd", "host_execution_readiness_authorization_review_runtime", LifecyclePhase.MAINTENANCE, {"correlation_id": correlation_id, "common_correlation_id": source_evaluation.correlation_id, "tick_id": tick_id, "source_privilege_review_evaluation_id": source_evaluation.evaluation_id, "source_privilege_review_evaluation_digest": source_evaluation.semantic_digest, "rehearsal_receipt_manifest_digest": manifest_digest, "runtime_plan_id": self.plan.plan_id, "runtime_plan_digest": self.plan.semantic_digest, "evidence_only": True, "no_effect_authority": True}))
    def run_cycle(self, *, tick_id: str, source_evaluation: HostPrivilegeReviewEvaluation | None, runtime_supervisor_report: Any | None = None, correlation_id: str | None = None, decision: ControlActionDecision | None = None, persist: bool = True) -> HostExecutionReadinessEvaluation | None:
        corr = correlation_id or f"{tick_id}:host_execution_readiness_authorization_review_runtime"
        if corr in self._by_correlation: return self._by_correlation[corr]
        if tick_id in self._tick_seen or source_evaluation is None: return None
        if getattr(source_evaluation, "no_effect_authority", False) is not True: return None
        manifest_digest = rehearsal_manifest_digest(source_evaluation)
        decision = decision or self.request_admission(tick_id=tick_id, correlation_id=corr, source_evaluation=source_evaluation, manifest_digest=manifest_digest)
        if not getattr(decision, "allowed", False): return None
        items: list[HostExecutionReadinessItem] = []; seen: dict[str,str] = {}
        for src in sorted(source_evaluation.items, key=lambda i:(i.source_receipt_id, i.item_id))[: self.plan.budget.max_items]:
            ref, findings = _source_ref(source_evaluation, src)
            if ref and ref.fulfillment_rehearsal_receipt_id in seen and seen[ref.fulfillment_rehearsal_receipt_id] != ref.fulfillment_rehearsal_receipt_digest: findings += ("duplicate_semantic_id_conflicting_digest",)
            if ref: seen[ref.fulfillment_rehearsal_receipt_id] = ref.fulfillment_rehearsal_receipt_digest
            if findings or ref is None:
                items.append(HostExecutionReadinessItem(_id("heri_", (src.item_id, findings)), ref, False, findings)); continue
            rr = src.fulfillment_rehearsal_receipt
            c = build_effect_receipt_contract(rr); f = build_future_effect_receipt_schema(c, created_at=self.clock()); p = build_postcondition_check_plan(c); r = build_rollback_plan(c)
            satisfied = ["rehearsal_required", "dry_run_required", "rollback_plan_required"]
            if runtime_supervisor_report is not None and getattr(runtime_supervisor_report, "degraded", False) is not True: satisfied.append("runtime_supervisor_observation_required")
            m = build_execution_readiness_manifest(c, f, p, r, runtime_supervisor_report=runtime_supervisor_report, satisfied_proof_gates=satisfied, created_at=self.clock())
            ap = build_authorization_review_packet(m); ad = evaluate_authorization_review(ap); ar = build_authorization_review_receipt(ad, created_at=self.clock()); ag = build_future_authorization_grant_schema(ar, created_at=self.clock())
            self.builder_call_count += 9
            item = HostExecutionReadinessItem(_id("heri_", (ref.to_dict(), c.contract_id, m.manifest_id, ap.packet_id, ad.decision_id)), ref, True, (), c, f, p, r, m, ap, ad, ar, ag)
            val = validate_item_chain(item)
            if not val.ok: item = HostExecutionReadinessItem(item.item_id, ref, False, val.findings, c, f, p, r, m, ap, ad, ar, ag)
            data = _canon(item.to_dict()).encode()
            if len(data) > self.plan.budget.max_serialized_item_bytes: item = HostExecutionReadinessItem(item.item_id, ref, False, ("serialized_item_exceeds_budget",), c, f, p, r, m, ap, ad, ar, ag)
            items.append(item)
        sem = {"schema": SCHEMA_VERSION, "plan": self.plan.semantic_digest, "source": source_evaluation.evaluation_id, "source_digest": source_evaluation.semantic_digest, "manifest": manifest_digest, "items": [i.item_id for i in items], "correlation_id": corr}
        eid = _id("here_", sem); cid = _id("herc_", sem)
        admission_ref = {"admission_decision_ref": decision.admission_decision_ref, "outcome": decision.outcome.value, "authority_class": decision.authority_class.value, "action_kind": decision.action_kind, "correlation_id": decision.correlation_id, "grants_operator_approval": False, "grants_future_effect_admission": False, "grants_fulfillment": False, "grants_execution": False}
        initial_findings: tuple[str,...] = ()
        ev = HostExecutionReadinessEvaluation(eid, cid, self.plan, admission_ref, source_evaluation.evaluation_id, source_evaluation.semantic_digest, manifest_digest, tick_id, corr, tuple(items), initial_findings, _summary(eid, cid, tuple(items), initial_findings), _sha(sem), self.clock(), True)
        val = validate_evaluation(ev)
        if not val.ok: ev = HostExecutionReadinessEvaluation(eid, cid, self.plan, admission_ref, source_evaluation.evaluation_id, source_evaluation.semantic_digest, manifest_digest, tick_id, corr, tuple(items), val.findings, _summary(eid, cid, tuple(items), val.findings), _sha(sem), ev.observed_at, True)
        self._by_correlation[corr] = ev; self._tick_seen.add(tick_id)
        if persist: persist_evidence_bundle(self.runtime_state_root, ev, tick_id=tick_id)
        return ev

def _safe_root(root: Path | str) -> Path:
    r = Path(root).resolve(); r.mkdir(parents=True, exist_ok=True)
    if r.is_symlink() or any(part == ".." for part in r.parts): raise ValueError("unsafe_runtime_state_root")
    return r

def render_markdown(evaluation: HostExecutionReadinessEvaluation) -> str:
    return "\n".join(["# Host Execution Readiness Authorization Review Runtime", "", f"- Evaluation: `{evaluation.evaluation_id}`", f"- Chain: `{evaluation.chain_id}`", f"- Source privilege review: `{evaluation.source_privilege_review_evaluation_id}`", f"- Valid/invalid items: `{evaluation.summary.valid_item_count}/{evaluation.summary.invalid_item_count}`", "- Authority: review only; no grant, fulfillment, execution, or host mutation.", ""])

def persist_evidence_bundle(root: Path | str, evaluation: HostExecutionReadinessEvaluation, *, tick_id: str) -> HostExecutionReadinessRuntimeReceipt:
    base = _safe_root(root) / "host_execution_readiness_runtime" / _id("tick_", {"tick": tick_id, "evaluation": evaluation.evaluation_id}); base.mkdir(parents=True, exist_ok=True)
    items = {"runtime_plan": evaluation.plan.to_dict(), "admission_reference": dict(evaluation.admission_ref), "source_privilege_review_evaluation_reference": {"evaluation_id": evaluation.source_privilege_review_evaluation_id, "digest": evaluation.source_privilege_review_evaluation_digest}, "source_rehearsal_manifest": {"digest": evaluation.source_rehearsal_manifest_digest}, "effect_receipt_contracts": [_to_dict(i.effect_receipt_contract) for i in evaluation.items if i.effect_receipt_contract is not None], "future_effect_receipt_schemas": [_to_dict(i.future_effect_receipt_schema) for i in evaluation.items if i.future_effect_receipt_schema is not None], "postcondition_plans": [_to_dict(i.postcondition_check_plan) for i in evaluation.items if i.postcondition_check_plan is not None], "rollback_plans": [_to_dict(i.rollback_plan) for i in evaluation.items if i.rollback_plan is not None], "execution_readiness_manifests": [_to_dict(i.execution_readiness_manifest) for i in evaluation.items if i.execution_readiness_manifest is not None], "authorization_review_packets": [_to_dict(i.authorization_review_packet) for i in evaluation.items if i.authorization_review_packet is not None], "authorization_review_decisions": [_to_dict(i.authorization_review_decision) for i in evaluation.items if i.authorization_review_decision is not None], "authorization_review_receipts": [_to_dict(i.authorization_review_receipt) for i in evaluation.items if i.authorization_review_receipt is not None], "future_authorization_grant_schemas": [_to_dict(i.future_authorization_grant_schema) for i in evaluation.items if i.future_authorization_grant_schema is not None], "item_validation_findings": {i.item_id: list(validate_item_chain(i).findings) for i in evaluation.items}, "runtime_receipt_compact": {"evaluation_id": evaluation.evaluation_id, "chain_id": evaluation.chain_id}, "summary": evaluation.summary.to_dict(), "items": [i.to_dict() for i in evaluation.items]}
    if len(items) > evaluation.plan.budget.max_bundle_files: raise ValueError("bundle_file_count_exceeds_budget")
    total = 0; paths: dict[str,str] = {}
    for name, obj in items.items():
        data = json.dumps(obj, sort_keys=True, indent=2, default=str).encode(); total += len(data)
        if total > evaluation.plan.budget.max_bundle_bytes: raise ValueError("bundle_size_exceeds_budget")
        target = base / f"{name}.json"; tmp = target.with_suffix(".json.tmp"); tmp.write_bytes(data); tmp.replace(target); paths[name] = target.as_posix()
    md = base / "summary.md"; tmp = md.with_suffix(".md.tmp"); tmp.write_text(render_markdown(evaluation), encoding="utf-8"); tmp.replace(md); paths["markdown"] = md.as_posix()
    bdig = digest(items); latest = base.parent / "latest.json"; lp = {"evaluation_id": evaluation.evaluation_id, "chain_id": evaluation.chain_id, "bundle_digest": bdig, "status": evaluation.summary.status, "read_only": True, "review_only": True, "authorization_granted": False, "execution_triggered": False}; tmp = latest.with_suffix(".json.tmp"); tmp.write_text(json.dumps(lp, sort_keys=True, indent=2), encoding="utf-8"); tmp.replace(latest)
    return HostExecutionReadinessRuntimeReceipt(_id("herr_", {"evaluation": evaluation.evaluation_id, "bundle": bdig}), evaluation.evaluation_id, bdig, base.as_posix(), paths, evaluation.semantic_digest)

def world_state_records(evaluation: HostExecutionReadinessEvaluation) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    base = {"source_kind": WorldStateSourceKind.FULFILLMENT.value, "schema_version": SCHEMA_VERSION, "observed_at": evaluation.observed_at, **NON_AUTHORITY}
    for it in evaluation.items:
        payload = {"chain_id": evaluation.chain_id, "source_privilege_review_evaluation_id": evaluation.source_privilege_review_evaluation_id, "required_gates": tuple(getattr(it.execution_readiness_manifest, "required_proof_gates", ()) or ()), "satisfied_gates": tuple(getattr(it.execution_readiness_manifest, "satisfied_proof_gates", ()) or ()), "missing_gates": tuple(getattr(it.execution_readiness_manifest, "missing_proof_gates", ()) or ()), "blocked_actions": tuple(getattr(it.execution_readiness_manifest, "blocked_actions", ()) or ()), "readiness_status": getattr(it.execution_readiness_manifest, "readiness_status", "invalid"), "authorization_review_status": getattr(it.authorization_review_decision, "decision_status", "invalid"), "findings": it.findings, "authorization_granted": False, "admission_granted": False, "fulfillment_granted": False, "host_mutation_performed": False}
        for kind, obj, digfun in (("effect_receipt_contract", it.effect_receipt_contract, effect_receipt_contract_digest), ("future_effect_receipt_schema", it.future_effect_receipt_schema, future_effect_receipt_digest), ("postcondition_check_plan", it.postcondition_check_plan, postcondition_check_plan_digest), ("rollback_plan", it.rollback_plan, rollback_plan_digest), ("execution_readiness_manifest", it.execution_readiness_manifest, execution_readiness_manifest_digest), ("authorization_review_packet", it.authorization_review_packet, lambda x: getattr(x, "source_execution_readiness_manifest_digest", "")), ("authorization_review_decision", it.authorization_review_decision, lambda x: _sha(_to_dict(x))), ("authorization_review_receipt", it.authorization_review_receipt, lambda x: getattr(x, "digest", "")), ("future_authorization_grant_schema", it.future_authorization_grant_schema, lambda x: getattr(x, "digest", ""))):
            if obj is None: continue
            records.append({**base, "source_id": f"her:{getattr(obj, 'contract_id', getattr(obj, 'receipt_id', getattr(obj, 'plan_id', getattr(obj, 'manifest_id', getattr(obj, 'packet_id', getattr(obj, 'decision_id', getattr(obj, 'schema_id', 'unknown')))))))}", "subject_id": getattr(obj, 'contract_id', getattr(obj, 'receipt_id', getattr(obj, 'plan_id', getattr(obj, 'manifest_id', getattr(obj, 'packet_id', getattr(obj, 'decision_id', getattr(obj, 'schema_id', 'unknown'))))))), "subject_kind": f"host_{kind}", "stage": "review", "disposition": payload["authorization_review_status"] if kind.startswith("authorization_review") else payload["readiness_status"], "payload": payload, "digest": digfun(obj)})
    return records

def summary_for_evaluation(evaluation: HostExecutionReadinessEvaluation) -> dict[str, Any]: return evaluation.summary.to_dict()
