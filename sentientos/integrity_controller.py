from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path

from sentientos.attestation import canonical_json_bytes, iso_now
from sentientos.attestation_snapshot import verify_recent_snapshots
from sentientos.audit_chain_gate import maybe_verify_audit_chain
from sentientos.doctrine_identity import verify_doctrine_identity
from sentientos.federation_integrity import federation_integrity_gate
from sentientos.integrity_pressure import compute_integrity_pressure
from sentientos.integrity_quarantine import load_state as load_quarantine_state
from sentientos.receipt_anchors import maybe_verify_receipt_anchors
from sentientos.receipt_chain import maybe_verify_receipt_chain
from sentientos.risk_budget import compute_risk_budget, risk_budget_summary
from sentientos.signed_rollups import latest_catalog_checkpoint_hash, verify_signed_rollups
from sentientos.signed_strategic import verify_recent
from sentientos.strategic_posture import resolve_posture
from sentientos.throughput_policy import derive_throughput_policy


@dataclass(frozen=True)
class IntegrityGateResult:
    name: str
    status: str
    reason: str
    evidence_paths: list[str]
    checked_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "reason": self.reason,
            "evidence_paths": list(self.evidence_paths),
            "checked_at": self.checked_at,
        }


@dataclass(frozen=True)
class IntegrityStatus:
    schema_version: int
    ts: str
    strategic_posture: str
    operating_mode: str
    pressure_summary: dict[str, object]
    quarantine_active: bool
    risk_budget_summary: dict[str, object]
    mutation_allowed: bool
    publish_allowed: bool
    automerge_allowed: bool
    gate_results: list[IntegrityGateResult]
    primary_reason: str
    reason_stack: list[str]
    recommended_actions: list[dict[str, object]]
    policy_hash: str
    budget_exhausted: bool
    budget_remaining: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "ts": self.ts,
            "strategic_posture": self.strategic_posture,
            "operating_mode": self.operating_mode,
            "pressure_summary": self.pressure_summary,
            "quarantine_active": self.quarantine_active,
            "risk_budget_summary": self.risk_budget_summary,
            "mutation_allowed": self.mutation_allowed,
            "publish_allowed": self.publish_allowed,
            "automerge_allowed": self.automerge_allowed,
            "gate_results": [item.to_dict() for item in self.gate_results],
            "primary_reason": self.primary_reason,
            "reason_stack": list(self.reason_stack),
            "recommended_actions": self.recommended_actions,
            "policy_hash": self.policy_hash,
            "budget_exhausted": self.budget_exhausted,
            "budget_remaining": dict(self.budget_remaining),
        }

    @property
    def status(self) -> str:
        values = {gate.status for gate in self.gate_results}
        if "fail" in values:
            return "fail"
        if "warn" in values:
            return "warn"
        return "ok"

    def canonical_hash(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()


@dataclass(frozen=True)
class IntegrityBudget:
    max_verify_streams_per_tick: int
    max_verify_items_per_stream: int
    max_snapshot_emits_per_window: int
    max_witness_attempts_per_window: int
    verification_cost_estimate: int

    @classmethod
    def from_env(cls) -> "IntegrityBudget":
        max_items = max(1, _env_int("SENTIENTOS_INTEGRITY_MAX_VERIFY_LAST_N", 25))
        return cls(
            max_verify_streams_per_tick=max(1, _env_int("SENTIENTOS_INTEGRITY_MAX_VERIFY_STREAMS", 3)),
            max_verify_items_per_stream=max_items,
            max_snapshot_emits_per_window=max(1, _env_int("SENTIENTOS_INTEGRITY_MAX_SNAPSHOT_PER_HOUR", 6)),
            max_witness_attempts_per_window=max(1, _env_int("SENTIENTOS_INTEGRITY_MAX_WITNESS_PER_HOUR", 6)),
            verification_cost_estimate=max_items,
        )


def evaluate_integrity(repo_root: Path, *, policy_hash: str, replay_mode: bool = False) -> IntegrityStatus:
    _ = replay_mode
    root = repo_root.resolve()
    checked_at = iso_now()
    quarantine = load_quarantine_state(root)
    pressure = compute_integrity_pressure(root)
    posture = resolve_posture()
    throughput = derive_throughput_policy(integrity_pressure_level=pressure.level, quarantine=quarantine)
    budget = compute_risk_budget(
        repo_root=root,
        posture=posture.posture,
        pressure_level=pressure.level,
        operating_mode=throughput.mode,
        quarantine_active=quarantine.active,
    )
    integrity_budget = IntegrityBudget.from_env()

    gates: list[IntegrityGateResult] = []
    gates.append(_gate_doctrine(root, checked_at))
    gates.append(_gate_receipt_chain(root, checked_at))
    gates.append(_gate_receipt_anchor(root, checked_at))
    gates.append(_gate_audit_chain(root, checked_at))
    verification_gates = _verification_budgeted_gates(root, checked_at, integrity_budget)
    gates.extend(verification_gates)
    gates.append(_gate_catalog_checkpoint(root, checked_at))
    gates.append(_gate_mypy_ratchet(root, checked_at))
    gates.append(_gate_federation_snapshot(root, checked_at))

    reason_stack = [gate.reason for gate in gates if gate.status in {"warn", "fail"}]
    primary_reason = reason_stack[0] if reason_stack else "integrity_ok"
    mutation_allowed = (not quarantine.active) and throughput.allow_forge_mutation and budget.forge_max_files_changed > 0
    if any(g.status == "fail" for g in gates):
        mutation_allowed = False
    publish_allowed = mutation_allowed and throughput.allow_publish and not quarantine.active
    automerge_allowed = publish_allowed and throughput.allow_automerge
    recommended_actions = _recommended_actions(gates)
    budget_exhausted = any(gate.reason == "skipped_budget_exhausted" for gate in verification_gates)
    used_verify_streams = sum(1 for gate in verification_gates if gate.reason != "skipped_budget_exhausted")
    budget_remaining = {
        "verify_streams": max(0, integrity_budget.max_verify_streams_per_tick - used_verify_streams),
        "verify_items_per_stream": integrity_budget.max_verify_items_per_stream,
        "snapshot_emits_per_window": integrity_budget.max_snapshot_emits_per_window,
        "witness_attempts_per_window": integrity_budget.max_witness_attempts_per_window,
    }
    return IntegrityStatus(
        schema_version=1,
        ts=checked_at,
        strategic_posture=posture.posture,
        operating_mode=throughput.mode,
        pressure_summary={"level": pressure.level, "metrics": pressure.metrics.to_dict()},
        quarantine_active=quarantine.active,
        risk_budget_summary=risk_budget_summary(budget),
        mutation_allowed=mutation_allowed,
        publish_allowed=publish_allowed,
        automerge_allowed=automerge_allowed,
        gate_results=gates,
        primary_reason=primary_reason,
        reason_stack=reason_stack,
        recommended_actions=recommended_actions,
        policy_hash=policy_hash,
        budget_exhausted=budget_exhausted,
        budget_remaining=budget_remaining,
    )


def _verification_budgeted_gates(root: Path, checked_at: str, budget: IntegrityBudget) -> list[IntegrityGateResult]:
    plans = [
        ("attestation_snapshot_signatures", _gate_snapshot_signatures),
        ("rollup_signatures", _gate_rollup_signatures),
        ("strategic_signatures", _gate_strategic_signatures),
    ]
    active = [name for name, fn in plans if fn(root, checked_at, budget, dry_run=True) is not None]
    priority = {"attestation_snapshot_signatures": 1, "rollup_signatures": 2, "strategic_signatures": 3}
    allowed = set(sorted(active, key=lambda name: priority[name], reverse=True)[: budget.max_verify_streams_per_tick])

    results: list[IntegrityGateResult] = []
    for name, fn in plans:
        gate = fn(root, checked_at, budget, dry_run=False)
        if gate is None:
            continue
        if name not in allowed:
            results.append(IntegrityGateResult(name=name, status="skipped", reason="skipped_budget_exhausted", evidence_paths=[], checked_at=checked_at))
            continue
        results.append(gate)
    return results


def _gate_doctrine(root: Path, checked_at: str) -> IntegrityGateResult:
    ok, payload = verify_doctrine_identity(root)
    mismatch = bool(payload.get("mismatch"))
    enforce = os.getenv("SENTIENTOS_DOCTRINE_IDENTITY_ENFORCE", "0") == "1"
    if mismatch and enforce:
        status = "fail"
    elif mismatch:
        status = "warn"
    else:
        status = "ok"
    return IntegrityGateResult("doctrine_identity", status, "doctrine_identity_mismatch" if mismatch else "ok", [], checked_at)


def _gate_receipt_chain(root: Path, checked_at: str) -> IntegrityGateResult:
    check, enforce, _warn = maybe_verify_receipt_chain(root, context="integrity_controller", last=_env_int("SENTIENTOS_RECEIPT_VERIFY_LAST_N", 25))
    if check is None:
        return IntegrityGateResult("receipt_chain", "skipped", "receipt_chain_disabled", [], checked_at)
    if check.ok:
        return IntegrityGateResult("receipt_chain", "ok", "ok", [], checked_at)
    return IntegrityGateResult("receipt_chain", "fail" if enforce else "warn", check.reason or "receipt_chain_failed", [], checked_at)


def _gate_receipt_anchor(root: Path, checked_at: str) -> IntegrityGateResult:
    check, enforce, _warn = maybe_verify_receipt_anchors(root, context="integrity_controller", last=_env_int("SENTIENTOS_ANCHOR_VERIFY_LAST_N", 10))
    if check is None:
        return IntegrityGateResult("receipt_anchors", "skipped", "receipt_anchors_disabled", [], checked_at)
    if check.ok:
        return IntegrityGateResult("receipt_anchors", "ok", "ok", [], checked_at)
    return IntegrityGateResult("receipt_anchors", "fail" if enforce else "warn", check.reason or "anchor_verify_failed", [], checked_at)


def _gate_audit_chain(root: Path, checked_at: str) -> IntegrityGateResult:
    check, enforce, _warn, report = maybe_verify_audit_chain(root, context="integrity_controller")
    if check is None:
        return IntegrityGateResult("audit_chain", "skipped", "audit_chain_disabled", [report] if report else [], checked_at)
    if check.ok:
        return IntegrityGateResult("audit_chain", "ok", "ok", [report] if report else [], checked_at)
    return IntegrityGateResult("audit_chain", "fail" if enforce else "warn", check.reason or "audit_chain_failed", [report] if report else [], checked_at)


def _gate_snapshot_signatures(root: Path, checked_at: str, budget: IntegrityBudget, *, dry_run: bool = False) -> IntegrityGateResult | None:
    if os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "0") != "1":
        return None
    if dry_run:
        return IntegrityGateResult("attestation_snapshot_signatures", "ok", "planned", [], checked_at)
    result = verify_recent_snapshots(root, last=budget.max_verify_items_per_stream)
    if result.status == "ok":
        return IntegrityGateResult("attestation_snapshot_signatures", "ok", "ok", [], checked_at)
    return IntegrityGateResult("attestation_snapshot_signatures", result.status, result.reason or "snapshot_signature_verify_failed", [], checked_at)


def _gate_rollup_signatures(root: Path, checked_at: str, budget: IntegrityBudget, *, dry_run: bool = False) -> IntegrityGateResult | None:
    if os.getenv("SENTIENTOS_ROLLUP_SIG_VERIFY", "0") != "1":
        return None
    if dry_run:
        return IntegrityGateResult("rollup_signatures", "ok", "planned", [], checked_at)
    ok, reason = verify_signed_rollups(root, last_weeks=max(1, min(_env_int("SENTIENTOS_ROLLUP_SIG_VERIFY_LAST_N", 6), budget.max_verify_items_per_stream)))
    if ok:
        return IntegrityGateResult("rollup_signatures", "ok", "ok", [], checked_at)
    enforce = os.getenv("SENTIENTOS_ROLLUP_SIG_ENFORCE", "0") == "1"
    return IntegrityGateResult("rollup_signatures", "fail" if enforce else "warn", reason or "rollup_signature_verify_failed", [], checked_at)


def _gate_strategic_signatures(root: Path, checked_at: str, budget: IntegrityBudget, *, dry_run: bool = False) -> IntegrityGateResult | None:
    if os.getenv("SENTIENTOS_STRATEGIC_SIG_VERIFY", "0") != "1":
        return None
    if dry_run:
        return IntegrityGateResult("strategic_signatures", "ok", "planned", [], checked_at)
    verification = verify_recent(root, last=max(1, min(_env_int("SENTIENTOS_STRATEGIC_SIG_VERIFY_LAST_N", 25), budget.max_verify_items_per_stream)))
    if verification.ok:
        return IntegrityGateResult("strategic_signatures", "ok", "ok", [], checked_at)
    enforce = os.getenv("SENTIENTOS_STRATEGIC_SIG_ENFORCE", "0") == "1"
    return IntegrityGateResult("strategic_signatures", "fail" if enforce else "warn", verification.reason or "strategic_signature_verify_failed", [], checked_at)


def _gate_catalog_checkpoint(root: Path, checked_at: str) -> IntegrityGateResult:
    tip = latest_catalog_checkpoint_hash(root)
    if tip:
        return IntegrityGateResult("catalog_checkpoint", "ok", "ok", [], checked_at)
    if os.getenv("SENTIENTOS_SIGN_CATALOG_CHECKPOINT", "0") == "1":
        return IntegrityGateResult("catalog_checkpoint", "warn", "catalog_checkpoint_missing", [], checked_at)
    return IntegrityGateResult("catalog_checkpoint", "skipped", "catalog_checkpoint_disabled", [], checked_at)


def _gate_mypy_ratchet(root: Path, checked_at: str) -> IntegrityGateResult:
    payload = _load_json(root / "glow/forge/ratchets/mypy_ratchet_status.json")
    if not payload:
        return IntegrityGateResult("mypy_ratchet", "skipped", "mypy_ratchet_missing", [], checked_at)
    status = str(payload.get("status") or "unknown")
    if status == "ok":
        return IntegrityGateResult("mypy_ratchet", "ok", "ok", ["glow/forge/ratchets/mypy_ratchet_status.json"], checked_at)
    return IntegrityGateResult("mypy_ratchet", "warn", "mypy_new_errors", ["glow/forge/ratchets/mypy_ratchet_status.json"], checked_at)


def _gate_federation_snapshot(root: Path, checked_at: str) -> IntegrityGateResult:
    gate = federation_integrity_gate(root, context="integrity_controller")
    status = str(gate.get("status") or "unknown")
    if status == "diverged":
        enforce = os.getenv("SENTIENTOS_FEDERATION_INTEGRITY_ENFORCE", "0") == "1"
        return IntegrityGateResult("federation_snapshot", "fail" if enforce else "warn", "federation_diverged", [], checked_at)
    if status == "ok":
        return IntegrityGateResult("federation_snapshot", "ok", "ok", [], checked_at)
    return IntegrityGateResult("federation_snapshot", "skipped", "no_peer_snapshot", [], checked_at)


def _recommended_actions(gates: list[IntegrityGateResult]) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    for gate in gates:
        if gate.status not in {"warn", "fail"}:
            continue
        if gate.name == "audit_chain":
            actions.append({"gate": gate.name, "kind": "script", "value": "python scripts/verify_audits.py --strict"})
        elif gate.name == "strategic_signatures":
            actions.append({"gate": gate.name, "kind": "script", "value": "python scripts/verify_strategic_signatures.py --last 25"})
        elif gate.name == "rollup_signatures":
            actions.append({"gate": gate.name, "kind": "script", "value": "python scripts/verify_rollup_signatures.py --last-weeks 6"})
        else:
            actions.append({"gate": gate.name, "kind": "note", "value": gate.reason})
    return actions


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
