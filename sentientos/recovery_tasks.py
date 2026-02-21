from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

TASKS_PATH = Path("pulse/recovery_tasks.jsonl")


def enqueue_mode_escalation_tasks(repo_root: Path, *, mode: str, reason: str, incident_id: str | None = None) -> list[dict[str, object]]:
    if mode not in {"recovery", "lockdown"}:
        return []
    rows = list_tasks(repo_root)
    existing_open = {(str(r.get("kind")), str(r.get("status", "open"))) for r in rows if str(r.get("status", "open")) != "done"}
    created: list[dict[str, object]] = []
    for kind, command in _default_commands():
        if (kind, "open") in existing_open:
            continue
        row = {
            "kind": kind,
            "created_at": _iso_now(),
            "reason": reason,
            "status": "open",
            "suggested_command": command,
            "related_incident_id": incident_id,
        }
        append_task_record(repo_root, row)
        created.append(row)
    return created


def append_task_record(repo_root: Path, row: dict[str, object]) -> None:
    path = repo_root.resolve() / TASKS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def mark_done(repo_root: Path, *, kind: str, note: str | None = None) -> dict[str, object]:
    row = {"kind": kind, "done_at": _iso_now(), "status": "done", "note": note or ""}
    append_task_record(repo_root, row)
    return row


def list_tasks(repo_root: Path) -> list[dict[str, object]]:
    path = repo_root.resolve() / TASKS_PATH
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


def backlog_count(repo_root: Path) -> int:
    open_kinds: set[str] = set()
    for row in list_tasks(repo_root):
        kind = str(row.get("kind", "")).strip()
        if not kind:
            continue
        status = str(row.get("status", "open"))
        if status == "done":
            open_kinds.discard(kind)
        else:
            open_kinds.add(kind)
    return len(open_kinds)


def _default_commands() -> list[tuple[str, str]]:
    return [
        ("audit_chain_doctor_repair_index", "python scripts/audit_chain_doctor.py --repair-index-only"),
        ("verify_receipt_chain", "python scripts/verify_receipt_chain.py --last 50"),
        ("verify_receipt_anchors", "python scripts/verify_receipt_anchors.py --last 10"),
        ("publish_anchor_witness", "python -m sentientos.anchor_witness"),
        ("emit_integrity_snapshot", "python -m sentientos.integrity_snapshot"),
    ]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
