"""Same-tick host proposal privilege review and fulfillment rehearsal runtime.

Evidence-only coordinator: consumes an existing HostResourceRuntimeEvaluation,
obtains proposal-evaluation admission, links host proposal receipts through the
Privilege Broker and Actuation Fulfillment dry-run builders, persists bounded
external artifacts, and emits World-State records. It never collects telemetry,
reevaluates host policy, authorizes effects, or mutates host state.
"""
from __future__ import annotations

import hashlib, json, os, tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sentientos.actuation_fulfillment import build_actuation_fulfillment_plan, build_actuation_fulfillment_rehearsal_receipt, actuation_fulfillment_plan_digest, validate_actuation_fulfillment_plan, validate_actuation_fulfillment_rehearsal_receipt
from sentientos.control_plane_kernel import AuthorityClass, ControlActionDecision, ControlActionRequest, ControlPlaneKernel, LifecyclePhase, get_control_plane_kernel
from sentientos.host_resource_policy import HOST_RESOURCE_PROPOSAL_KINDS, HostResourceProposalReceipt, host_resource_proposal_receipt_digest, validate_host_resource_proposal_receipt
from sentientos.host_resource_runtime import HostResourceRuntimeEvaluation, canonical_json
from sentientos.privilege_broker import build_privilege_broker_review_receipt, evaluate_privilege_broker_eligibility, privilege_broker_decision_digest, validate_privilege_broker_eligibility_decision, validate_privilege_broker_review_receipt
from sentientos.world_state_board import WorldStateSourceKind, digest

SCHEMA_VERSION = "host_privilege_review_rehearsal_runtime.v1"
REQUIRED_PROPOSAL_KINDS = tuple(sorted(HOST_RESOURCE_PROPOSAL_KINDS))
OPTIONAL_PROPOSAL_KINDS: tuple[str, ...] = ()
NON_EFFECT_FLAGS = {
    "effect_claimed": False,
    "effect_proven": False,
    "admission_granted": False,
    "fulfillment_granted": False,
    "host_mutation_performed": False,
}


def _id(prefix: str, value: Any) -> str:
    return prefix + hashlib.sha256(canonical_json(value).encode()).hexdigest()[:24]

def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _to_dict(value: Any) -> dict[str, Any]: return asdict(value) if hasattr(value, "__dataclass_fields__") else dict(value)
def _sha(value: Any) -> str: return hashlib.sha256(canonical_json(value).encode()).hexdigest()

@dataclass(frozen=True)
class HostPrivilegeReviewBudget:
    max_source_receipts: int = 32
    max_serialized_bytes: int = 262144
    retry_count: int = 0
    max_bundle_files: int = 12
    max_bundle_bytes: int = 1048576
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostPrivilegeReviewPlan:
    plan_id: str
    semantic_digest: str
    budget: HostPrivilegeReviewBudget
    required_proposal_kinds: tuple[str, ...] = REQUIRED_PROPOSAL_KINDS
    optional_proposal_kinds: tuple[str, ...] = OPTIONAL_PROPOSAL_KINDS
    authority_class: str = AuthorityClass.PROPOSAL_EVALUATION.value
    metadata_only: bool = True
    rehearsal_only: bool = True
    effect_authority: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostPrivilegeReviewItem:
    item_id: str
    source_receipt_id: str
    source_receipt_digest: str
    source_proposal_kind: str
    source_status: str
    valid_source: bool
    findings: tuple[str, ...]
    broker_decision: Any | None = None
    broker_review_receipt: Any | None = None
    fulfillment_plan: Any | None = None
    fulfillment_rehearsal_receipt: Any | None = None
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostPrivilegeReviewRuntimeSummary:
    status: str
    evaluation_id: str
    chain_id: str
    source_proposal_count: int
    valid_source_count: int
    invalid_source_count: int
    broker_decision_count: int
    rehearsal_plan_count: int
    rehearsal_receipt_count: int
    findings: tuple[str, ...]
    read_only: bool = True
    rehearsal_only: bool = True
    collection_triggered: bool = False
    privileged_execution_triggered: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostPrivilegeReviewEvaluation:
    evaluation_id: str
    chain_id: str
    plan: HostPrivilegeReviewPlan
    admission_ref: Mapping[str, Any]
    source_host_evaluation_id: str
    source_host_evaluation_digest: str
    source_tick_id: str
    correlation_id: str
    proposal_receipt_manifest: Mapping[str, Any]
    items: tuple[HostPrivilegeReviewItem, ...]
    validation_findings: tuple[str, ...]
    summary: HostPrivilegeReviewRuntimeSummary
    semantic_digest: str
    observed_at: str
    no_effect_authority: bool = True
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostPrivilegeReviewReceipt:
    receipt_id: str
    evaluation_id: str
    bundle_digest: str
    artifact_root: str
    artifact_paths: Mapping[str, str]
    semantic_digest: str
    no_effect_authority: bool = True
    repository_mutation_performed: bool = False
    host_mutation_performed: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class HostPrivilegeReviewRuntimeValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()

def build_host_privilege_review_plan(budget: HostPrivilegeReviewBudget | None = None) -> HostPrivilegeReviewPlan:
    b = budget or HostPrivilegeReviewBudget()
    sem = {"budget": b.to_dict(), "required": REQUIRED_PROPOSAL_KINDS, "optional": OPTIONAL_PROPOSAL_KINDS, "schema": SCHEMA_VERSION}
    return HostPrivilegeReviewPlan(_id("hprp_", sem), _id("hprps_", sem), b)

def _proposal_digest(receipt: HostResourceProposalReceipt) -> str:
    return str(receipt.digest or host_resource_proposal_receipt_digest(receipt))

def build_proposal_manifest(evaluation: HostResourceRuntimeEvaluation, plan: HostPrivilegeReviewPlan) -> dict[str, Any]:
    entries = []
    for receipt in sorted(evaluation.proposal_receipts, key=lambda r: (r.proposal_kind, r.receipt_id))[: plan.budget.max_source_receipts]:
        entries.append({"receipt_id": receipt.receipt_id, "digest": _proposal_digest(receipt), "proposal_kind": receipt.proposal_kind, "proposal_status": receipt.proposal_status})
    manifest = {"schema_version": SCHEMA_VERSION, "source_evaluation_id": evaluation.evaluation_id, "source_evaluation_digest": evaluation.semantic_digest, "entries": entries, "count": len(entries)}
    return {**manifest, "manifest_digest": _sha(manifest)}

def _validate_source(receipt: HostResourceProposalReceipt, evaluation: HostResourceRuntimeEvaluation, seen: dict[str, str]) -> tuple[bool, tuple[str, ...]]:
    findings: list[str] = []
    actual = host_resource_proposal_receipt_digest(receipt)
    claimed = receipt.digest or actual
    if receipt.digest and receipt.digest != actual: findings.append("receipt_digest_mismatch")
    if receipt.receipt_id in seen and seen[receipt.receipt_id] != claimed: findings.append("duplicate_receipt_id_conflicting_digest")
    seen[receipt.receipt_id] = claimed
    if receipt.report_id != evaluation.pressure_report.report_id: findings.append("pressure_report_mismatch")
    if receipt.report_digest != evaluation.policy_decision.report_digest: findings.append("policy_report_digest_mismatch")
    if receipt.decision_id != evaluation.policy_decision.decision_id: findings.append("policy_decision_mismatch")
    if receipt.proposal_kind not in HOST_RESOURCE_PROPOSAL_KINDS: findings.append("unsupported_proposal_kind")
    if not receipt.proposal_only or not receipt.does_not_execute or not receipt.does_not_mutate_host or not receipt.not_authorized_for_fulfillment: findings.append("source_claims_effect_or_authority")
    findings.extend(validate_host_resource_proposal_receipt(receipt).findings)
    return (not findings, tuple(sorted(set(findings))))

def validate_evaluation(evaluation: HostPrivilegeReviewEvaluation) -> HostPrivilegeReviewRuntimeValidationResult:
    findings = list(evaluation.validation_findings)
    if not evaluation.no_effect_authority: findings.append("effect_authority_true")
    if evaluation.summary.host_mutation_performed or evaluation.summary.privileged_execution_triggered: findings.append("summary_claims_effect")
    for item in evaluation.items:
        if not item.valid_source:
            continue
        if item.broker_decision is None or item.broker_review_receipt is None or item.fulfillment_plan is None or item.fulfillment_rehearsal_receipt is None:
            findings.append(f"{item.source_receipt_id}:missing_downstream_chain")
            continue
        findings.extend(f"{item.source_receipt_id}:broker_decision:{x}" for x in validate_privilege_broker_eligibility_decision(item.broker_decision).findings)
        findings.extend(f"{item.source_receipt_id}:broker_receipt:{x}" for x in validate_privilege_broker_review_receipt(item.broker_review_receipt).findings)
        findings.extend(f"{item.source_receipt_id}:fulfillment_plan:{x}" for x in validate_actuation_fulfillment_plan(item.fulfillment_plan).findings)
        findings.extend(f"{item.source_receipt_id}:rehearsal_receipt:{x}" for x in validate_actuation_fulfillment_rehearsal_receipt(item.fulfillment_rehearsal_receipt).findings)
        if item.broker_decision.source_receipt_digest != item.source_receipt_digest: findings.append(f"{item.source_receipt_id}:broker_source_digest_mismatch")
        if item.broker_review_receipt.source_receipt_digest != item.source_receipt_digest: findings.append(f"{item.source_receipt_id}:review_source_digest_mismatch")
        if item.fulfillment_plan.source_broker_receipt_digest != item.broker_review_receipt.digest: findings.append(f"{item.source_receipt_id}:plan_broker_digest_mismatch")
        if item.fulfillment_rehearsal_receipt.source_broker_receipt_digest != item.broker_review_receipt.digest: findings.append(f"{item.source_receipt_id}:rehearsal_broker_digest_mismatch")
    return HostPrivilegeReviewRuntimeValidationResult(not findings, tuple(sorted(set(findings))))

class HostPrivilegeReviewRuntimeCoordinator:
    def __init__(self, *, kernel: ControlPlaneKernel | None = None, runtime_state_root: Path | str | None = None, plan: HostPrivilegeReviewPlan | None = None, clock: Callable[[], str] | None = None) -> None:
        self.kernel = kernel or get_control_plane_kernel(); self.runtime_state_root = Path(runtime_state_root or os.getenv("SENTIENTOS_RUNTIME_STATE_ROOT") or (tempfile.gettempdir()+"/sentientos_runtime")); self.plan = plan or build_host_privilege_review_plan(); self.clock = clock or _now; self._by_correlation: dict[str, HostPrivilegeReviewEvaluation] = {}; self._tick_seen: set[str] = set(); self.builder_call_count = 0
    def request_admission(self, *, tick_id: str, correlation_id: str, source_evaluation: HostResourceRuntimeEvaluation, manifest: Mapping[str, Any]) -> ControlActionDecision:
        return self.kernel.admit(ControlActionRequest("host_privilege_review_rehearsal_runtime", AuthorityClass.PROPOSAL_EVALUATION, "sentientosd", "host_privilege_review_rehearsal_runtime", LifecyclePhase.MAINTENANCE, {"correlation_id": correlation_id, "tick_id": tick_id, "source_host_evaluation_id": source_evaluation.evaluation_id, "source_host_evaluation_digest": source_evaluation.semantic_digest, "proposal_receipt_manifest_digest": manifest.get("manifest_digest"), "runtime_plan_id": self.plan.plan_id, "metadata_only": True, "rehearsal_only": True, "no_effect_authority": True}))
    def run_cycle(self, *, tick_id: str, source_evaluation: HostResourceRuntimeEvaluation | None, correlation_id: str | None = None, decision: ControlActionDecision | None = None, persist: bool = True) -> HostPrivilegeReviewEvaluation | None:
        corr = correlation_id or f"{tick_id}:host_privilege_review_rehearsal_runtime"
        if corr in self._by_correlation: return self._by_correlation[corr]
        if tick_id in self._tick_seen: return None
        if source_evaluation is None: return None
        if getattr(source_evaluation, "no_effect_authority", False) is not True: return None
        if source_evaluation.validation_findings: return None
        manifest = build_proposal_manifest(source_evaluation, self.plan)
        if len(canonical_json(manifest).encode()) > self.plan.budget.max_serialized_bytes: return None
        decision = decision or self.request_admission(tick_id=tick_id, correlation_id=corr, source_evaluation=source_evaluation, manifest=manifest)
        if not getattr(decision, "allowed", False): return None
        seen: dict[str, str] = {}; items: list[HostPrivilegeReviewItem] = []
        for receipt in sorted(source_evaluation.proposal_receipts, key=lambda r: (r.proposal_kind, r.receipt_id))[: self.plan.budget.max_source_receipts]:
            valid, findings = _validate_source(receipt, source_evaluation, seen)
            src_digest = _proposal_digest(receipt)
            if not valid:
                items.append(HostPrivilegeReviewItem(_id("hpri_", (receipt.receipt_id, src_digest, findings)), receipt.receipt_id, src_digest, receipt.proposal_kind, receipt.proposal_status, False, findings))
                continue
            bd = evaluate_privilege_broker_eligibility(receipt); br = build_privilege_broker_review_receipt(bd, created_at=self.clock()); fp = build_actuation_fulfillment_plan(br); rr = build_actuation_fulfillment_rehearsal_receipt(fp, created_at=self.clock()); self.builder_call_count += 4
            items.append(HostPrivilegeReviewItem(_id("hpri_", (receipt.receipt_id, src_digest, bd.decision_id, br.receipt_id, fp.plan_id, rr.receipt_id)), receipt.receipt_id, src_digest, receipt.proposal_kind, receipt.proposal_status, True, (), bd, br, fp, rr))
        sem = {"plan": self.plan.semantic_digest, "source": source_evaluation.evaluation_id, "source_digest": source_evaluation.semantic_digest, "manifest": manifest["manifest_digest"], "items": [i.item_id for i in items], "correlation_id": corr}
        eid = _id("hpre_", sem); chain_id = _id("hprc_", sem)
        summary = _summary(eid, chain_id, tuple(items), ())
        admission_ref = {"admission_decision_ref": decision.admission_decision_ref, "outcome": decision.outcome.value, "authority_class": decision.authority_class.value, "action_kind": decision.action_kind, "correlation_id": decision.correlation_id, "grants_privileged_execution": False, "grants_fulfillment": False}
        ev = HostPrivilegeReviewEvaluation(eid, chain_id, self.plan, admission_ref, source_evaluation.evaluation_id, source_evaluation.semantic_digest, tick_id, corr, manifest, tuple(items), (), summary, _id("hpres_", sem), self.clock(), True)
        validation = validate_evaluation(ev)
        if not validation.ok:
            ev = HostPrivilegeReviewEvaluation(eid, chain_id, self.plan, admission_ref, source_evaluation.evaluation_id, source_evaluation.semantic_digest, tick_id, corr, manifest, tuple(items), validation.findings, _summary(eid, chain_id, tuple(items), validation.findings), _id("hpres_", sem), ev.observed_at, True)
        self._by_correlation[corr] = ev; self._tick_seen.add(tick_id)
        if persist: persist_evidence_bundle(self.runtime_state_root, ev, tick_id=tick_id)
        return ev

def _summary(evaluation_id: str, chain_id: str, items: tuple[HostPrivilegeReviewItem, ...], findings: Sequence[str]) -> HostPrivilegeReviewRuntimeSummary:
    valid = sum(1 for i in items if i.valid_source)
    status = "degraded" if findings or valid != len(items) else "ok"
    return HostPrivilegeReviewRuntimeSummary(status, evaluation_id, chain_id, len(items), valid, len(items)-valid, sum(i.broker_decision is not None for i in items), sum(i.fulfillment_plan is not None for i in items), sum(i.fulfillment_rehearsal_receipt is not None for i in items), tuple(findings))

def summary_for_evaluation(evaluation: HostPrivilegeReviewEvaluation) -> dict[str, Any]: return evaluation.summary.to_dict()

def render_markdown(evaluation: HostPrivilegeReviewEvaluation) -> str:
    return "\n".join(["# Host Privilege Review Rehearsal Runtime", "", f"- Evaluation: `{evaluation.evaluation_id}`", f"- Chain: `{evaluation.chain_id}`", f"- Source host evaluation: `{evaluation.source_host_evaluation_id}`", f"- Source proposals: `{evaluation.summary.source_proposal_count}`", f"- Valid/invalid: `{evaluation.summary.valid_source_count}/{evaluation.summary.invalid_source_count}`", "- Effects: `none`; rehearsal is not execution.", ""])

def _safe_root(root: Path | str) -> Path:
    root = Path(root).resolve()
    if any(part == ".." for part in root.parts): raise ValueError("traversal rejected")
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink(): raise ValueError("symlink root rejected")
    return root

def persist_evidence_bundle(root: Path | str, evaluation: HostPrivilegeReviewEvaluation, *, tick_id: str) -> HostPrivilegeReviewReceipt:
    base = _safe_root(root) / "host_privilege_review_runtime" / _id("tick_", {"tick": tick_id, "evaluation": evaluation.evaluation_id})
    base.mkdir(parents=True, exist_ok=True)
    items = {
        "runtime_plan": evaluation.plan.to_dict(), "admission_reference": dict(evaluation.admission_ref), "source_host_evaluation_reference": {"evaluation_id": evaluation.source_host_evaluation_id, "digest": evaluation.source_host_evaluation_digest}, "proposal_receipt_manifest": dict(evaluation.proposal_receipt_manifest),
        "broker_decisions": [_to_dict(i.broker_decision) for i in evaluation.items if i.broker_decision is not None], "broker_review_receipts": [_to_dict(i.broker_review_receipt) for i in evaluation.items if i.broker_review_receipt is not None], "fulfillment_rehearsal_plans": [_to_dict(i.fulfillment_plan) for i in evaluation.items if i.fulfillment_plan is not None], "fulfillment_rehearsal_receipts": [_to_dict(i.fulfillment_rehearsal_receipt) for i in evaluation.items if i.fulfillment_rehearsal_receipt is not None], "chain_validation_findings": list(evaluation.validation_findings), "summary": evaluation.summary.to_dict(), "items": [i.to_dict() for i in evaluation.items]}
    if len(items) > evaluation.plan.budget.max_bundle_files: raise ValueError("bundle_file_count_exceeds_budget")
    paths: dict[str, str] = {}; total = 0
    for name, obj in items.items():
        data = json.dumps(obj, sort_keys=True, indent=2, default=str).encode(); total += len(data)
        if total > evaluation.plan.budget.max_bundle_bytes: raise ValueError("bundle_size_exceeds_budget")
        target = base / f"{name}.json"; tmp = target.with_suffix(".json.tmp"); tmp.write_bytes(data); tmp.replace(target); paths[name] = target.as_posix()
    md = base / "summary.md"; tmp = md.with_suffix(".md.tmp"); tmp.write_text(render_markdown(evaluation), encoding="utf-8"); tmp.replace(md); paths["markdown"] = md.as_posix()
    bdig = digest(items); latest = base.parent / "latest.json"; lp = {"evaluation_id": evaluation.evaluation_id, "chain_id": evaluation.chain_id, "bundle_digest": bdig, "posture": evaluation.summary.status, "read_only": True, "rehearsal_only": True}; tmp = latest.with_suffix(".json.tmp"); tmp.write_text(json.dumps(lp, sort_keys=True, indent=2), encoding="utf-8"); tmp.replace(latest)
    return HostPrivilegeReviewReceipt(_id("hprr_", {"evaluation": evaluation.evaluation_id, "bundle": bdig}), evaluation.evaluation_id, bdig, base.as_posix(), paths, evaluation.semantic_digest)

def world_state_records(evaluation: HostPrivilegeReviewEvaluation) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    base = {"source_kind": WorldStateSourceKind.PRIVILEGE.value, "schema_version": SCHEMA_VERSION, "observed_at": evaluation.observed_at, **NON_EFFECT_FLAGS}
    for item in evaluation.items:
        payload = {"chain_id": evaluation.chain_id, "source_host_evaluation_id": evaluation.source_host_evaluation_id, "source_receipt_id": item.source_receipt_id, "source_receipt_digest": item.source_receipt_digest, "required_future_gates": tuple(getattr(item.broker_decision, "required_future_gates", ())), "blocked_actions": tuple(getattr(item.broker_decision, "blocked_actions", ())), "valid_source": item.valid_source, "findings": item.findings}
        common = {**base, "payload": payload}
        records.append({**common, "source_id": f"hpr:{item.source_receipt_id}:source", "subject_id": item.source_receipt_id, "subject_kind": "host_privilege_review_source_proposal", "stage": "proposal", "disposition": "recorded" if item.valid_source else "contradicted", "digest": item.source_receipt_digest})
        if item.broker_decision is not None:
            records.append({**common, "source_id": f"hpr:{item.broker_decision.decision_id}", "subject_id": item.broker_decision.decision_id, "subject_kind": "host_privilege_broker_eligibility", "stage": "review", "disposition": item.broker_decision.eligibility_status.replace("privilege_broker_", ""), "digest": privilege_broker_decision_digest(item.broker_decision)})
        if item.broker_review_receipt is not None:
            records.append({**common, "source_id": f"hpr:{item.broker_review_receipt.receipt_id}", "subject_id": item.broker_review_receipt.receipt_id, "subject_kind": "host_privilege_broker_review_receipt", "stage": "review", "disposition": item.broker_review_receipt.review_status.replace("privilege_broker_receipt_", ""), "digest": item.broker_review_receipt.digest})
        if item.fulfillment_plan is not None:
            records.append({**common, "source_kind": WorldStateSourceKind.FULFILLMENT.value, "source_id": f"hpr:{item.fulfillment_plan.plan_id}", "subject_id": item.fulfillment_plan.plan_id, "subject_kind": "host_fulfillment_rehearsal_plan", "stage": "review", "disposition": item.fulfillment_plan.plan_status.replace("actuation_fulfillment_plan_", ""), "payload": {**payload, "rehearsal_only": True}, "digest": actuation_fulfillment_plan_digest(item.fulfillment_plan)})
        if item.fulfillment_rehearsal_receipt is not None:
            records.append({**common, "source_kind": WorldStateSourceKind.FULFILLMENT.value, "source_id": f"hpr:{item.fulfillment_rehearsal_receipt.receipt_id}", "subject_id": item.fulfillment_rehearsal_receipt.receipt_id, "subject_kind": "host_fulfillment_rehearsal_receipt", "stage": "review", "disposition": item.fulfillment_rehearsal_receipt.rehearsal_status.replace("actuation_fulfillment_rehearsal_", ""), "payload": {**payload, "rehearsal_only": True}, "digest": item.fulfillment_rehearsal_receipt.digest})
    return records
