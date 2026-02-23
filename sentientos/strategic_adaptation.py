from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from sentientos.artifact_catalog import CATALOG_PATH, append_catalog_entry
from sentientos.audit_chain_gate import maybe_verify_audit_chain
from sentientos.goal_graph import Goal, GoalGraph, GoalStateRecord, goal_graph_hash, load_goal_graph, load_goal_state, persist_goal_graph
from sentientos.integrity_pressure import compute_integrity_pressure
from sentientos.integrity_quarantine import load_state as load_quarantine_state
from sentientos.receipt_anchors import maybe_verify_receipt_anchors
from sentientos.receipt_chain import maybe_verify_receipt_chain

PROPOSALS_DIR = Path("glow/forge/strategic/proposals")
CHANGES_DIR = Path("glow/forge/strategic/changes")
PROPOSALS_PULSE_PATH = Path("pulse/strategic_proposals.jsonl")
CHANGES_PULSE_PATH = Path("pulse/strategic_changes.jsonl")


@dataclass(frozen=True)
class AnalysisWindow:
    name: str
    start: str
    end: str


@dataclass(frozen=True)
class Guardrails:
    max_weight_delta_per_proposal: float
    max_goals_changed: int
    forbidden_tags: tuple[str, ...]


@dataclass(frozen=True)
class Adjustment:
    goal_id: str
    field: str
    old: object
    new: object
    reason: str
    evidence_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["evidence_paths"] = list(self.evidence_paths)
        return payload


@dataclass(frozen=True)
class Approval:
    status: str
    approved_by: str | None
    decision_notes: str


@dataclass(frozen=True)
class GoalGraphAdjustmentProposal:
    schema_version: int
    proposal_id: str
    created_at: str
    base_goal_graph_hash: str
    window: AnalysisWindow
    inputs_summary: dict[str, object]
    adjustments: tuple[Adjustment, ...]
    predicted_effects: tuple[str, ...]
    guardrails: Guardrails
    approval: Approval

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "created_at": self.created_at,
            "base_goal_graph_hash": self.base_goal_graph_hash,
            "window": asdict(self.window),
            "inputs_summary": self.inputs_summary,
            "adjustments": [item.to_dict() for item in self.adjustments],
            "predicted_effects": list(self.predicted_effects),
            "guardrails": asdict(self.guardrails),
            "approval": asdict(self.approval),
        }


def create_adjustment_proposal(
    repo_root: Path,
    *,
    window_name: str = "last_24h",
    now: datetime | None = None,
    max_weight_delta_per_proposal: float = 0.2,
    max_goals_changed: int = 5,
    forbidden_tags: tuple[str, ...] = ("integrity_core",),
) -> tuple[GoalGraphAdjustmentProposal, str]:
    root = repo_root.resolve()
    graph = load_goal_graph(root)
    goal_state = load_goal_state(root)
    point = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
    window = _resolve_window(window_name, point)

    metrics = _compute_inputs_summary(root=root, window=window, goal_state=goal_state)
    adjustments, effects = _compute_adjustments(
        graph=graph,
        goal_state=goal_state,
        summary=metrics,
        max_weight_delta=max_weight_delta_per_proposal,
        max_goals_changed=max_goals_changed,
        forbidden_tags=set(forbidden_tags),
    )
    evidence_digest = hashlib.sha256(json.dumps(metrics, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:8]
    graph_digest = goal_graph_hash(graph)
    proposal_id = f"{_safe_ts(window.end)}_{graph_digest[:8]}_{evidence_digest}"
    proposal = GoalGraphAdjustmentProposal(
        schema_version=1,
        proposal_id=proposal_id,
        created_at=window.end,
        base_goal_graph_hash=graph_digest,
        window=window,
        inputs_summary=metrics,
        adjustments=tuple(adjustments),
        predicted_effects=tuple(effects),
        guardrails=Guardrails(
            max_weight_delta_per_proposal=max_weight_delta_per_proposal,
            max_goals_changed=max_goals_changed,
            forbidden_tags=tuple(sorted(forbidden_tags)),
        ),
        approval=Approval(status="proposed", approved_by=None, decision_notes=""),
    )
    proposal_path = _persist_proposal(root, proposal)
    return proposal, proposal_path


def approve_proposal(
    repo_root: Path,
    *,
    proposal_path: Path,
    approve: bool,
    approved_by: str,
    decision_notes: str,
    apply: bool,
    enforce_stable: bool,
) -> tuple[GoalGraphAdjustmentProposal, str | None]:
    root = repo_root.resolve()
    proposal = _load_proposal(proposal_path)
    new_approval = Approval(status="approved" if approve else "rejected", approved_by=approved_by, decision_notes=decision_notes)
    updated = GoalGraphAdjustmentProposal(
        schema_version=proposal.schema_version,
        proposal_id=proposal.proposal_id,
        created_at=proposal.created_at,
        base_goal_graph_hash=proposal.base_goal_graph_hash,
        window=proposal.window,
        inputs_summary=proposal.inputs_summary,
        adjustments=proposal.adjustments,
        predicted_effects=proposal.predicted_effects,
        guardrails=proposal.guardrails,
        approval=new_approval,
    )
    _write_json(proposal_path, updated.to_dict())
    change_id: str | None = None
    if approve and apply:
        if enforce_stable and not strategic_apply_preconditions(root):
            return updated, None
        change_id = apply_approved_proposal(root, updated, approved_by=approved_by)
    return updated, change_id


def apply_approved_proposal(repo_root: Path, proposal: GoalGraphAdjustmentProposal, *, approved_by: str) -> str:
    root = repo_root.resolve()
    graph = load_goal_graph(root)
    old_hash = goal_graph_hash(graph)
    goals_by_id = {goal.goal_id: goal for goal in graph.goals}
    for adj in proposal.adjustments:
        existing = goals_by_id.get(adj.goal_id)
        if existing is None:
            continue
        goals_by_id[adj.goal_id] = _apply_adjustment(existing, adj)

    new_graph = GoalGraph(schema_version=1, goals=tuple(goals_by_id.values()))
    persist_goal_graph(root, new_graph)
    new_hash = goal_graph_hash(new_graph)
    change_id = f"change_{_safe_ts(_iso_now())}_{proposal.proposal_id}"
    rel_path = CHANGES_DIR / f"{change_id}.json"
    payload = {
        "schema_version": 1,
        "change_id": change_id,
        "proposal_id": proposal.proposal_id,
        "applied_at": _iso_now(),
        "approved_by": approved_by,
        "old_goal_graph_hash": old_hash,
        "new_goal_graph_hash": new_hash,
        "diff_summary": [adj.to_dict() for adj in proposal.adjustments],
    }
    _write_json(root / rel_path, payload)
    _append_jsonl(
        root / CHANGES_PULSE_PATH,
        {
            "change_id": change_id,
            "proposal_id": proposal.proposal_id,
            "approved_by": approved_by,
            "applied_at": payload["applied_at"],
            "old_goal_graph_hash": old_hash,
            "new_goal_graph_hash": new_hash,
            "path": str(rel_path),
        },
    )
    append_catalog_entry(
        root,
        kind="strategic_change",
        artifact_id=change_id,
        relative_path=str(rel_path),
        schema_name="strategic_change",
        schema_version=1,
        links={"proposal_id": proposal.proposal_id, "goal_graph_hash": new_hash},
        summary={"status": "applied", "approved_by": approved_by},
        ts=payload["applied_at"],
    )
    return change_id


def strategic_apply_preconditions(repo_root: Path) -> bool:
    root = repo_root.resolve()
    pressure = compute_integrity_pressure(root)
    quarantine = load_quarantine_state(root)
    if pressure.level > 1 or quarantine.active:
        return False
    chain_check, _, _ = maybe_verify_receipt_chain(root, context="strategic_apply", last=10)
    anchor_check, _, _ = maybe_verify_receipt_anchors(root, context="strategic_apply", last=10)
    audit_check, _, _, _ = maybe_verify_audit_chain(root, context="strategic_apply")
    return bool(chain_check is not None and chain_check.ok) and bool(anchor_check is not None and anchor_check.ok) and bool(audit_check is not None and audit_check.ok)


def can_auto_apply() -> bool:
    return os.getenv("SENTIENTOS_STRATEGIC_AUTO_APPLY", "0") == "1"


def auto_propose_enabled() -> bool:
    return os.getenv("SENTIENTOS_STRATEGIC_AUTO_PROPOSE", "0") == "1"


def apply_requires_stable() -> bool:
    return os.getenv("SENTIENTOS_STRATEGIC_APPLY_REQUIRE_STABLE", "1") == "1"


def strategic_cooldown_until(repo_root: Path) -> str | None:
    rows = _read_jsonl(repo_root.resolve() / PROPOSALS_PULSE_PATH)
    if not rows:
        return None
    latest = rows[-1]
    created = _parse_iso(_as_str(latest.get("created_at")))
    if created is None:
        return None
    return _iso((created + timedelta(days=1)).replace(microsecond=0))


def should_generate_proposal(repo_root: Path, *, now: datetime | None = None) -> bool:
    point = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
    rows = _read_jsonl(repo_root.resolve() / PROPOSALS_PULSE_PATH)
    if not rows:
        return True
    latest = _parse_iso(_as_str(rows[-1].get("created_at")))
    if latest is None:
        return True
    return point - latest >= timedelta(days=1)


def _compute_inputs_summary(*, root: Path, window: AnalysisWindow, goal_state: dict[str, GoalStateRecord]) -> dict[str, object]:
    start = _parse_iso(window.start)
    end = _parse_iso(window.end)
    assert start is not None and end is not None
    incidents_rows, incidents_source = _rows_in_window(root, "integrity_incidents", start, end)
    ticks_rows, ticks_source = _rows_in_window(root, "orchestrator_ticks", start, end)
    attempts_rows, _ = _rows_in_window(root, "auto_remediation_attempts", start, end)

    incidents_by_trigger: dict[str, int] = {}
    quarantine_activations = 0
    for row in incidents_rows:
        triggers = row.get("triggers") if isinstance(row.get("triggers"), list) else []
        for trigger in triggers:
            if isinstance(trigger, str) and trigger:
                incidents_by_trigger[trigger] = incidents_by_trigger.get(trigger, 0) + 1
        if bool(row.get("quarantine_activated")):
            quarantine_activations += 1

    pressure_distribution: dict[str, int] = {}
    remediation_total = 0
    remediation_success = 0
    for row in ticks_rows:
        level = int(row.get("integrity_pressure_level", 0))
        key = str(level)
        pressure_distribution[key] = pressure_distribution.get(key, 0) + 1
        remediation = str(row.get("remediation_status", ""))
        if remediation:
            remediation_total += 1
            if remediation in {"succeeded", "idle"}:
                remediation_success += 1

    completed = sum(1 for item in goal_state.values() if item.status == "completed")
    blocked = sum(1 for item in goal_state.values() if item.status == "blocked")
    active = sum(1 for item in goal_state.values() if item.status == "active")

    block_reasons: dict[str, int] = {}
    for item in goal_state.values():
        if item.status == "blocked" and item.blocked_reason:
            reason = str(item.blocked_reason)
            block_reasons[reason] = block_reasons.get(reason, 0) + 1

    evidence_paths = _collect_evidence_paths(root, incidents_rows, ticks_rows)
    remediation_success_rate = 1.0 if remediation_total == 0 else round(remediation_success / remediation_total, 4)
    return {
        "incidents_by_trigger": dict(sorted(incidents_by_trigger.items())),
        "pressure_level_distribution": dict(sorted(pressure_distribution.items())),
        "quarantine_activations": quarantine_activations,
        "remediation_success_rate": remediation_success_rate,
        "goal_outcomes": {"completed": completed, "blocked": blocked, "active": active},
        "top_block_reasons": [{"reason": reason, "count": count} for reason, count in sorted(block_reasons.items(), key=lambda item: (-item[1], item[0]))[:5]],
        "evidence_paths": evidence_paths,
        "sources": {"incidents": incidents_source, "orchestrator_ticks": ticks_source, "remediation_attempts_count": len(attempts_rows)},
    }


def _compute_adjustments(
    *,
    graph: GoalGraph,
    goal_state: dict[str, GoalStateRecord],
    summary: dict[str, object],
    max_weight_delta: float,
    max_goals_changed: int,
    forbidden_tags: set[str],
) -> tuple[list[Adjustment], list[str]]:
    del goal_state
    adjustments: list[Adjustment] = []
    effects: list[str] = []
    pressure_distribution = summary.get("pressure_level_distribution") if isinstance(summary.get("pressure_level_distribution"), dict) else {}
    frequent_high_pressure = sum(int(v) for k, v in pressure_distribution.items() if str(k).isdigit() and int(k) >= 2 and isinstance(v, int)) >= 2
    quarantine_activations = int(summary.get("quarantine_activations", 0))
    remediation_success_rate = float(summary.get("remediation_success_rate", 0.0))
    top_block_reasons = summary.get("top_block_reasons") if isinstance(summary.get("top_block_reasons"), list) else []
    evidence_paths = tuple(str(item) for item in list(summary.get("evidence_paths") or [])[:6] if isinstance(item, str))

    sorted_goals = sorted(graph.goals, key=lambda g: (str(g.goal_id)))
    integrity_goals = [g for g in sorted_goals if ("integrity" in g.tags or "stability" in g.tags)]
    feature_goals = [g for g in sorted_goals if ("feature" in g.tags or "perf" in g.tags)]

    if frequent_high_pressure or quarantine_activations >= 1:
        effects.append("reduce_integrity_debt")
        for goal in integrity_goals[:2]:
            new_weight = min(1.0, round(goal.weight + min(max_weight_delta, 0.1), 4))
            if new_weight != goal.weight:
                adjustments.append(Adjustment(goal.goal_id, "weight", goal.weight, new_weight, "high_pressure_or_quarantine", evidence_paths))
        for goal in feature_goals[:2]:
            if len(adjustments) >= max_goals_changed:
                break
            new_weight = max(0.0, round(goal.weight - min(max_weight_delta, 0.05), 4))
            if new_weight != goal.weight:
                adjustments.append(Adjustment(goal.goal_id, "weight", goal.weight, new_weight, "reduce_feature_churn_under_pressure", evidence_paths))

    for entry in top_block_reasons:
        if len(adjustments) >= max_goals_changed:
            break
        if not isinstance(entry, dict):
            continue
        reason = str(entry.get("reason", ""))
        count = int(entry.get("count", 0))
        if count < 2:
            continue
        for goal in sorted_goals:
            if any(tag in forbidden_tags for tag in goal.tags):
                continue
            if goal.enabled:
                adjustments.append(Adjustment(goal.goal_id, "priority", goal.priority, max(0, goal.priority - 1), f"repeated_block:{reason}", evidence_paths))
                break

    if remediation_success_rate >= 0.8 and not frequent_high_pressure and quarantine_activations == 0:
        effects.append("restore_baseline_weights")
        for goal in sorted_goals:
            if len(adjustments) >= max_goals_changed:
                break
            baseline = _baseline_weight_for_goal(goal)
            if abs(goal.weight - baseline) < 0.0001:
                continue
            delta = min(max_weight_delta, 0.05)
            if goal.weight > baseline:
                new_weight = max(baseline, round(goal.weight - delta, 4))
            else:
                new_weight = min(baseline, round(goal.weight + delta, 4))
            adjustments.append(Adjustment(goal.goal_id, "weight", goal.weight, new_weight, "remediation_stable_restore", evidence_paths))

    deduped: list[Adjustment] = []
    seen: set[tuple[str, str]] = set()
    for item in adjustments:
        key = (item.goal_id, item.field)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= max_goals_changed:
            break

    bounded: list[Adjustment] = []
    for item in deduped:
        if item.field == "weight":
            old = float(item.old)
            new = float(item.new)
            if abs(new - old) > max_weight_delta:
                new = old + max_weight_delta if new > old else old - max_weight_delta
                item = Adjustment(item.goal_id, item.field, round(old, 4), round(new, 4), item.reason, item.evidence_paths)
        bounded.append(item)
    if not effects:
        effects.append("hold_graph_constant")
    return bounded, effects


def _baseline_weight_for_goal(goal: Goal) -> float:
    if "integrity" in goal.tags or "stability" in goal.tags:
        return 0.7
    if "feature" in goal.tags or "perf" in goal.tags:
        return 0.4
    return 0.5


def _apply_adjustment(goal: Goal, adjustment: Adjustment) -> Goal:
    if adjustment.field == "weight":
        return replace(goal, weight=float(adjustment.new))
    if adjustment.field == "priority":
        return replace(goal, priority=int(adjustment.new))
    if adjustment.field == "enabled":
        return replace(goal, enabled=bool(adjustment.new))
    return goal


def _resolve_window(name: str, end: datetime) -> AnalysisWindow:
    if name == "last_7d":
        start = end - timedelta(days=7)
    else:
        name = "last_24h"
        start = end - timedelta(hours=24)
    return AnalysisWindow(name=name, start=_iso(start), end=_iso(end))


def _rows_in_window(root: Path, stream: str, start: datetime, end: datetime) -> tuple[list[dict[str, object]], str]:
    if _has_rollup_for_window(root, stream, start, end):
        rows = _read_jsonl(root / "pulse" / f"{stream}.jsonl")
        return [row for row in rows if _in_window(row, start, end)], "rollup+stream"
    rows = _read_jsonl(root / "pulse" / f"{stream}.jsonl")
    return [row for row in rows if _in_window(row, start, end)], "stream"


def _has_rollup_for_window(root: Path, stream: str, start: datetime, end: datetime) -> bool:
    rollup_dir = root / "glow/forge/rollups" / stream
    if not rollup_dir.exists():
        return False
    for week in _weeks_in_range(start, end):
        if (rollup_dir / f"rollup_{week}.json").exists():
            return True
    return False


def _weeks_in_range(start: datetime, end: datetime) -> list[str]:
    weeks: list[str] = []
    cursor = start
    while cursor <= end:
        wk = f"{cursor.isocalendar().year}-{cursor.isocalendar().week:02d}"
        if wk not in weeks:
            weeks.append(wk)
        cursor += timedelta(days=1)
    return weeks


def _in_window(row: dict[str, object], start: datetime, end: datetime) -> bool:
    timestamp = _parse_iso(_extract_ts(row))
    if timestamp is None:
        return False
    return start <= timestamp <= end


def _extract_ts(row: dict[str, object]) -> str | None:
    for key in ("generated_at", "created_at", "ts", "attempted_at", "timestamp"):
        raw = row.get(key)
        if isinstance(raw, str) and raw:
            return raw
    return None


def _collect_evidence_paths(root: Path, incidents_rows: list[dict[str, object]], ticks_rows: list[dict[str, object]]) -> list[str]:
    paths: list[str] = []
    for row in incidents_rows:
        path = row.get("path")
        if isinstance(path, str) and path:
            paths.append(path)
    for row in ticks_rows:
        path = row.get("tick_report_path")
        if isinstance(path, str) and path:
            paths.append(path)
    catalog = _read_jsonl(root / CATALOG_PATH)
    for row in catalog[-10:]:
        kind = row.get("kind")
        if isinstance(kind, str) and kind.startswith("strategic_"):
            continue
        rel = row.get("path")
        if isinstance(rel, str) and rel:
            paths.append(rel)
    return sorted(set(paths))[:12]


def _persist_proposal(root: Path, proposal: GoalGraphAdjustmentProposal) -> str:
    rel_path = PROPOSALS_DIR / f"proposal_{_safe_ts(proposal.created_at)}.json"
    _write_json(root / rel_path, proposal.to_dict())
    _append_jsonl(
        root / PROPOSALS_PULSE_PATH,
        {
            "created_at": proposal.created_at,
            "proposal_id": proposal.proposal_id,
            "status": proposal.approval.status,
            "path": str(rel_path),
            "base_goal_graph_hash": proposal.base_goal_graph_hash,
            "adjustment_count": len(proposal.adjustments),
        },
    )
    append_catalog_entry(
        root,
        kind="strategic_proposal",
        artifact_id=proposal.proposal_id,
        relative_path=str(rel_path),
        schema_name="strategic_proposal",
        schema_version=proposal.schema_version,
        links={"proposal_id": proposal.proposal_id, "goal_graph_hash": proposal.base_goal_graph_hash},
        summary={"status": proposal.approval.status, "adjustments": len(proposal.adjustments)},
        ts=proposal.created_at,
    )
    return str(rel_path)


def _load_proposal(path: Path) -> GoalGraphAdjustmentProposal:
    payload = _load_json(path)
    window_raw = payload.get("window") if isinstance(payload.get("window"), dict) else {}
    approval_raw = payload.get("approval") if isinstance(payload.get("approval"), dict) else {}
    guardrails_raw = payload.get("guardrails") if isinstance(payload.get("guardrails"), dict) else {}
    adjustments_raw = payload.get("adjustments") if isinstance(payload.get("adjustments"), list) else []
    adjustments = tuple(
        Adjustment(
            goal_id=str(row.get("goal_id", "")),
            field=str(row.get("field", "")),
            old=row.get("old"),
            new=row.get("new"),
            reason=str(row.get("reason", "")),
            evidence_paths=tuple(str(item) for item in row.get("evidence_paths", []) if isinstance(item, str)),
        )
        for row in adjustments_raw
        if isinstance(row, dict)
    )
    return GoalGraphAdjustmentProposal(
        schema_version=int(payload.get("schema_version", 1)),
        proposal_id=str(payload.get("proposal_id", "proposal")),
        created_at=str(payload.get("created_at", _iso_now())),
        base_goal_graph_hash=str(payload.get("base_goal_graph_hash", "")),
        window=AnalysisWindow(name=str(window_raw.get("name", "last_24h")), start=str(window_raw.get("start", "")), end=str(window_raw.get("end", ""))),
        inputs_summary=payload.get("inputs_summary") if isinstance(payload.get("inputs_summary"), dict) else {},
        adjustments=adjustments,
        predicted_effects=tuple(str(item) for item in payload.get("predicted_effects", []) if isinstance(item, str)),
        guardrails=Guardrails(
            max_weight_delta_per_proposal=float(guardrails_raw.get("max_weight_delta_per_proposal", 0.2)),
            max_goals_changed=int(guardrails_raw.get("max_goals_changed", 5)),
            forbidden_tags=tuple(str(item) for item in guardrails_raw.get("forbidden_tags", []) if isinstance(item, str)),
        ),
        approval=Approval(
            status=str(approval_raw.get("status", "proposed")),
            approved_by=_as_str(approval_raw.get("approved_by")),
            decision_notes=str(approval_raw.get("decision_notes", "")),
        ),
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _append_jsonl(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _iso_now() -> str:
    return _iso(datetime.now(timezone.utc))


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
