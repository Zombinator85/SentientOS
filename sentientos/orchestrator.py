from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any

from sentientos.anchor_witness import maybe_publish_anchor_witness
from sentientos.auto_remediation import maybe_auto_run_pack
from sentientos.audit_chain_gate import maybe_verify_audit_chain
from sentientos.doctrine_identity import verify_doctrine_identity
from sentientos.federation_integrity import federation_integrity_gate
from sentientos.forge_index import INDEX_PATH, rebuild_index
from sentientos.governance_trace import start_governance_trace
from sentientos.integrity_pressure import compute_integrity_pressure, update_pressure_state
from sentientos.integrity_quarantine import load_state as load_quarantine_state
from sentientos.integrity_snapshot import PEER_SNAPSHOTS_DIR, SNAPSHOT_PATH, emit_integrity_snapshot
from sentientos.receipt_anchors import maybe_verify_receipt_anchors
from sentientos.receipt_chain import maybe_verify_receipt_chain
from sentientos.remediation_pack import PACKS_PULSE_PATH
from sentientos.recovery_tasks import backlog_count
from sentientos.risk_budget import compute_risk_budget, risk_budget_summary
from sentientos.strategic_posture import resolve_posture
from sentientos.throughput_policy import derive_throughput_policy
from sentientos.schema_registry import LATEST_VERSIONS, latest_version, SchemaName


@dataclass(frozen=True)
class OrchestratorConfig:
    enabled: bool
    interval_seconds: int
    sweeps_enabled: bool
    auto_remediation_enabled: bool
    federation_snapshot_enabled: bool
    witness_publish_enabled: bool

    @classmethod
    def from_env(cls) -> "OrchestratorConfig":
        return cls(
            enabled=os.getenv("SENTIENTOS_ORCHESTRATOR_ENABLE", "0") == "1",
            interval_seconds=max(5, _env_int("SENTIENTOS_ORCHESTRATOR_INTERVAL_SECONDS", 300)),
            sweeps_enabled=os.getenv("SENTIENTOS_ORCHESTRATOR_SWEEPS", "1") == "1",
            auto_remediation_enabled=os.getenv("SENTIENTOS_ORCHESTRATOR_AUTO_REMEDIATION", "1") == "1",
            federation_snapshot_enabled=os.getenv("SENTIENTOS_ORCHESTRATOR_FEDERATION_SNAPSHOT", "1") == "1",
            witness_publish_enabled=os.getenv("SENTIENTOS_ORCHESTRATOR_WITNESS_PUBLISH", "0") == "1",
        )


@dataclass(frozen=True)
class TickResult:
    tick_at: str
    status: str
    operating_mode: str
    integrity_pressure_level: int
    trace_id: str | None
    remediation_status: str
    index_path: str
    tick_report_path: str


def tick(repo_root: Path, *, config: OrchestratorConfig | None = None, daemon_active: bool = False) -> TickResult:
    root = repo_root.resolve()
    cfg = config or OrchestratorConfig.from_env()
    now = _iso_now()

    quarantine = load_quarantine_state(root)
    pressure = compute_integrity_pressure(root)
    _pressure_state, pressure_changed = update_pressure_state(root, pressure)
    throughput = derive_throughput_policy(integrity_pressure_level=pressure.level, quarantine=quarantine)
    posture = resolve_posture()
    budget = compute_risk_budget(
        repo_root=root,
        posture=posture.posture,
        pressure_level=pressure.level,
        operating_mode=throughput.mode,
        quarantine_active=quarantine.active,
    )

    mutation_allowed = (not quarantine.active) and budget.forge_max_files_changed > 0

    trace = start_governance_trace(
        repo_root=root,
        context="orchestrator_tick",
        strategic_posture=posture.posture,
        integrity_pressure_level=pressure.level,
        integrity_metrics_summary=pressure.metrics.to_dict(),
        operating_mode=throughput.mode,
        mode_toggles_summary={
            "allow_automerge": throughput.allow_automerge,
            "allow_publish": throughput.allow_publish,
            "allow_forge_mutation": throughput.allow_forge_mutation,
        },
        quarantine_state_summary={
            "active": quarantine.active,
            "allow_publish": quarantine.allow_publish,
            "allow_automerge": quarantine.allow_automerge,
            "last_incident_id": quarantine.last_incident_id,
        },
        risk_budget_summary=risk_budget_summary(budget),
        risk_budget_notes=[str(item) for item in list(budget.notes or [])[:8]],
    )

    sweep_summary: dict[str, object] | None = None
    federation_snapshot_path: str | None = None
    peer_snapshot_count = 0
    witness_status = "disabled"
    witness_failure: str | None = None
    remediation_status = "idle"
    remediation_detail: dict[str, object] | None = None
    reason_stack: list[str] = []

    if cfg.sweeps_enabled and throughput.mode in {"cautious", "recovery", "lockdown"}:
        if _should_run_sweep(root, interval_minutes=posture.diagnostics_sweep_interval_minutes):
            sweep_summary = _run_integrity_sweep(root=root, pressure_level=pressure.level, mode=throughput.mode)
            trace.record_gate(
                name="diagnostics_sweep",
                mode="warn",
                result="pass" if int((sweep_summary.get("summary") or {}).get("failed", 0)) == 0 else "hold",
                reason="orchestrator_sweep",
                evidence_paths=[str(sweep_summary.get("artifact_path", ""))],
            )
            if int((sweep_summary.get("summary") or {}).get("failed", 0)) > 0:
                reason_stack.append("diagnostics_sweep_failures")

    if cfg.auto_remediation_enabled:
        if not mutation_allowed:
            remediation_status = "skipped"
            remediation_detail = {"reason": "mutation_disallowed"}
            trace.record_gate(name="auto_remediation", mode="enforce", result="hold", reason="mutation_disallowed")
            reason_stack.append("mutation_disallowed")
        else:
            pack = _latest_eligible_pack(root)
            if pack is None:
                remediation_status = "idle"
                remediation_detail = {"reason": "no_eligible_pack"}
            else:
                decision = maybe_auto_run_pack(
                    root,
                    operating_mode=throughput.mode,
                    context="orchestrator_tick",
                    pack=pack,
                    governance_trace_id="orchestrator_pending",
                    incident_id=_optional_str(pack.get("incident_id")),
                )
                remediation_status = decision.status
                remediation_detail = {
                    "reason": decision.reason,
                    "attempted": decision.attempted,
                    "pack_id": decision.pack_id,
                    "run_id": decision.run_id,
                }
                trace.record_gate(
                    name="auto_remediation",
                    mode="warn",
                    result="pass" if decision.status in {"succeeded", "idle"} else "hold",
                    reason=decision.reason,
                    evidence_paths=[str(pack.get("pack_path", ""))],
                )
                if decision.status not in {"idle", "succeeded"}:
                    reason_stack.append(f"auto_remediation_{decision.status}")

    if cfg.federation_snapshot_enabled:
        snapshot = emit_integrity_snapshot(root)
        federation_snapshot_path = str(SNAPSHOT_PATH)
        if daemon_active:
            peer_snapshot_count = _peer_snapshot_count(root)
        _ = snapshot

    if cfg.witness_publish_enabled:
        if mutation_allowed:
            previous = os.getenv("SENTIENTOS_ANCHOR_WITNESS_PUBLISH")
            os.environ["SENTIENTOS_ANCHOR_WITNESS_PUBLISH"] = "1"
            status_payload, failure = maybe_publish_anchor_witness(root)
            if previous is None:
                os.environ.pop("SENTIENTOS_ANCHOR_WITNESS_PUBLISH", None)
            else:
                os.environ["SENTIENTOS_ANCHOR_WITNESS_PUBLISH"] = previous
            witness_status = str(status_payload.get("witness_status") or "unknown")
            witness_failure = _optional_str(failure) or _optional_str(status_payload.get("witness_failure"))
        else:
            witness_status = "skipped"
            witness_failure = "mutation_disallowed"

    rebuild_index(root)

    backlog = {
        "recovery_task_backlog_count": backlog_count(root),
        "remediation_backlog_count": _remediation_backlog_count(root),
    }
    status = "ok"
    if witness_failure or remediation_status in {"failed", "cooldown"}:
        status = "warning"
    if pressure_changed and pressure.level >= 3:
        status = "warning"

    final_reason_stack = reason_stack or ["orchestrator_tick"]
    trace_response = trace.finalize(
        final_decision="diagnostics_only" if not mutation_allowed else "allow",
        final_reason="orchestrator_tick_completed",
        reason_stack=final_reason_stack,
        suggested_actions=["python scripts/orchestrator_tick.py"],
    )

    trace_id = _optional_str(trace_response.get("trace_id"))
    trace_path = _optional_str(trace_response.get("trace_path"))
    linked_pack = trace_response.get("remediation_pack") if isinstance(trace_response.get("remediation_pack"), dict) else None

    report = {
        "schema_version": latest_version(SchemaName.ORCHESTRATOR_TICK),
        "generated_at": now,
        "status": status,
        "orchestrator_enabled": cfg.enabled,
        "operating_mode": throughput.mode,
        "integrity_pressure_level": pressure.level,
        "quarantine_active": quarantine.active,
        "mutation_allowed": mutation_allowed,
        "risk_budget_summary": risk_budget_summary(budget),
        "last_sweep": sweep_summary,
        "auto_remediation": remediation_detail,
        "federation_snapshot": {
            "path": federation_snapshot_path,
            "peer_snapshot_count": peer_snapshot_count,
        },
        "witness_publish": {
            "status": witness_status,
            "failure": witness_failure,
        },
        "trace": {
            "trace_id": trace_id,
            "trace_path": trace_path,
            "linked_remediation_pack": linked_pack,
        },
        "orchestrator_backlog_summary": backlog,
        "index_path": str(INDEX_PATH),
        "schema_versions_snapshot": dict(sorted(LATEST_VERSIONS.items())),
    }
    tick_path = root / "glow/forge/orchestrator/ticks" / f"tick_{_safe_ts(now)}.json"
    tick_path.parent.mkdir(parents=True, exist_ok=True)
    tick_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    pulse_row = {
        "generated_at": now,
        "status": status,
        "operating_mode": throughput.mode,
        "integrity_pressure_level": pressure.level,
        "remediation_status": remediation_status,
        "tick_report_path": str(tick_path.relative_to(root)),
    }
    _append_jsonl(root / "pulse/orchestrator_ticks.jsonl", pulse_row)

    _write_orchestrator_index_overlay(
        root,
        orchestrator_enabled=cfg.enabled,
        generated_at=now,
        status=status,
        backlog=backlog,
        tick_report_path=str(tick_path.relative_to(root)),
    )

    return TickResult(
        tick_at=now,
        status=status,
        operating_mode=throughput.mode,
        integrity_pressure_level=pressure.level,
        trace_id=trace_id,
        remediation_status=remediation_status,
        index_path=str(INDEX_PATH),
        tick_report_path=str(tick_path.relative_to(root)),
    )


def _latest_eligible_pack(repo_root: Path) -> dict[str, object] | None:
    rows = _read_jsonl(repo_root / PACKS_PULSE_PATH)
    for row in reversed(rows):
        if str(row.get("status", "")) in {"proposed", "queued"}:
            return row
    return None


def _should_run_sweep(repo_root: Path, *, interval_minutes: int) -> bool:
    rows = _read_jsonl(repo_root / "pulse/sweeps.jsonl")
    if not rows:
        return True
    latest = _optional_str(rows[-1].get("generated_at"))
    parsed = _parse_iso(latest)
    if parsed is None:
        return True
    return datetime.now(timezone.utc) - parsed >= timedelta(minutes=max(1, interval_minutes))


def _run_integrity_sweep(*, root: Path, pressure_level: int, mode: str) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    doctrine_ok, doctrine_payload = verify_doctrine_identity(root)
    checks.append({"name": "verify_doctrine_identity", "ok": doctrine_ok, "detail": doctrine_payload})

    chain_check, _enforce, _warn = maybe_verify_receipt_chain(root, context="orchestrator_sweep", last=50)
    checks.append({"name": "verify_receipt_chain", "ok": bool(chain_check.ok) if chain_check is not None else True, "detail": chain_check.to_dict() if chain_check is not None else {}})

    anchor_check, _a_enforce, _a_warn = maybe_verify_receipt_anchors(root, context="orchestrator_sweep", last=10)
    checks.append({"name": "verify_receipt_anchors", "ok": bool(anchor_check.ok) if anchor_check is not None else True, "detail": anchor_check.to_dict() if anchor_check is not None else {}})

    audit_check, _audit_enforce, _audit_warn, audit_report = maybe_verify_audit_chain(root, context="orchestrator_sweep")
    checks.append({"name": "verify_audits_strict", "ok": bool(audit_check.ok) if audit_check is not None else True, "detail": audit_check.to_dict() if audit_check is not None else {}, "report_path": audit_report})

    federation = federation_integrity_gate(root, context="orchestrator_sweep")
    checks.append({"name": "federation_integrity_snapshot_compare", "ok": not bool(federation.get("blocked")), "detail": federation})

    passed = sum(1 for row in checks if bool(row.get("ok")))
    failed = len(checks) - passed
    generated_at = _iso_now()
    payload = {"mode": mode, "pressure_level": pressure_level, "generated_at": generated_at, "checks": checks, "summary": {"passed": passed, "failed": failed}}
    sweep_path = root / f"glow/forge/sweeps/sweep_{_safe_ts(generated_at)}.json"
    sweep_path.parent.mkdir(parents=True, exist_ok=True)
    sweep_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _append_jsonl(root / "pulse/sweeps.jsonl", {"generated_at": generated_at, "mode": mode, "summary": payload["summary"], "path": str(sweep_path.relative_to(root))})
    return {"artifact_path": str(sweep_path.relative_to(root)), "summary": payload["summary"]}


def _write_orchestrator_index_overlay(
    repo_root: Path,
    *,
    orchestrator_enabled: bool,
    generated_at: str,
    status: str,
    backlog: dict[str, int],
    tick_report_path: str,
) -> None:
    path = repo_root / INDEX_PATH
    payload = _load_json(path)
    payload["schema_version"] = latest_version(SchemaName.FORGE_INDEX)
    payload["orchestrator_enabled"] = orchestrator_enabled
    payload["last_orchestrator_tick_at"] = generated_at
    payload["last_orchestrator_tick_status"] = status
    payload["orchestrator_backlog_summary"] = backlog
    payload["last_tick_report_path"] = tick_report_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _peer_snapshot_count(repo_root: Path) -> int:
    return len(list((repo_root / PEER_SNAPSHOTS_DIR).glob("*/integrity_snapshot.json")))


def _remediation_backlog_count(repo_root: Path) -> int:
    rows = _read_jsonl(repo_root / "pulse/recovery_tasks.jsonl")
    total = 0
    for row in rows:
        if str(row.get("status", "open")) == "done":
            continue
        if str(row.get("kind", "")).startswith("remediation_pack:"):
            total += 1
    return total


def _append_jsonl(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_ts(value: str) -> str:
    return value.replace(":", "-").replace(".", "-")


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
