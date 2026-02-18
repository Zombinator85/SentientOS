"""Forge Observatory artifact index and compaction helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
INDEX_PATH = Path("glow/forge/index.json")
QUEUE_PATH = Path("pulse/forge_queue.jsonl")
RECEIPTS_PATH = Path("pulse/forge_receipts.jsonl")
RECEIPTS_COMPACTED_PATH = Path("glow/forge/receipts_snapshot.json")
QUEUE_COMPACTED_PATH = Path("glow/forge/queue_snapshot.json")


def rebuild_index(repo_root: Path) -> dict[str, Any]:
    """Rebuild the canonical forge observability index."""

    root = repo_root.resolve()
    reports = sorted((root / "glow/forge").glob("report_*.json"), key=lambda item: item.name)
    dockets = sorted((root / "glow/forge").glob("docket_*.json"), key=lambda item: item.name)

    queue_rows, queue_corrupt = _read_jsonl(root / QUEUE_PATH)
    receipt_rows, receipt_corrupt = _read_jsonl(root / RECEIPTS_PATH)

    index: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _iso_now(),
        "latest_reports": [_load_json(path) | {"path": str(path.relative_to(root))} for path in reports[-50:]],
        "latest_dockets": [_load_json(path) | {"path": str(path.relative_to(root))} for path in dockets[-50:]],
        "latest_receipts": receipt_rows[-200:],
        "latest_queue": _pending_from_rows(queue_rows, receipt_rows),
        "env_cache": _env_cache_summary(root),
        "ci_baseline_latest": _load_json(root / "glow/contracts/ci_baseline.json") or None,
        "corrupt_count": {
            "queue": queue_corrupt,
            "receipts": receipt_corrupt,
            "total": queue_corrupt + receipt_corrupt,
        },
    }

    target = root / INDEX_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index


def update_index_incremental(repo_root: Path, *, event: dict[str, object] | None = None) -> dict[str, Any]:
    """Incremental index refresh. Falls back to full rebuild for correctness."""

    _ = event
    return rebuild_index(repo_root)


def compact_jsonl(
    repo_root: Path,
    *,
    receipts_keep_last: int = 200,
    queue_keep_last: int = 200,
) -> dict[str, Any]:
    """Create compacted snapshots and prune old JSONL rows."""

    root = repo_root.resolve()
    queue_rows, queue_corrupt = _read_jsonl(root / QUEUE_PATH)
    receipt_rows, receipt_corrupt = _read_jsonl(root / RECEIPTS_PATH)

    _write_json(root / QUEUE_COMPACTED_PATH, {"schema_version": 1, "rows": queue_rows, "corrupt_count": queue_corrupt})
    _write_json(root / RECEIPTS_COMPACTED_PATH, {"schema_version": 1, "rows": receipt_rows, "corrupt_count": receipt_corrupt})

    _write_jsonl(root / QUEUE_PATH, queue_rows[-queue_keep_last:])
    _write_jsonl(root / RECEIPTS_PATH, receipt_rows[-receipts_keep_last:])
    return {
        "queue_rows": len(queue_rows),
        "receipts_rows": len(receipt_rows),
        "queue_corrupt": queue_corrupt,
        "receipts_corrupt": receipt_corrupt,
    }


def _read_jsonl(path: Path) -> tuple[list[dict[str, object]], int]:
    if not path.exists():
        return ([], 0)
    rows: list[dict[str, object]] = []
    corrupt = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                corrupt += 1
                continue
            if isinstance(payload, dict):
                rows.append(payload)
            else:
                corrupt += 1
    return (rows, corrupt)


def _pending_from_rows(queue_rows: list[dict[str, object]], receipt_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    consumed = {
        row.get("request_id")
        for row in receipt_rows
        if row.get("status") in {"started", "success", "failed", "skipped_budget", "rejected_policy"}
    }
    pending = [row for row in queue_rows if row.get("request_id") not in consumed]
    def _priority(row: dict[str, object]) -> int:
        value = row.get("priority")
        return value if isinstance(value, int) else 100

    pending.sort(key=lambda item: (_priority(item), str(item.get("requested_at", "")), str(item.get("request_id", ""))))
    return pending


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _env_cache_summary(repo_root: Path) -> dict[str, object]:
    cache_path = repo_root / "glow/forge/env_cache.json"
    payload = _load_json(cache_path)
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return {"entries": 0, "newest": None, "oldest": None, "total_size_bytes": 0}
    valid_entries = [item for item in entries if isinstance(item, dict)]
    last_used = [str(item.get("last_used_at")) for item in valid_entries if isinstance(item.get("last_used_at"), str)]
    sizes = [size for item in valid_entries for size in [item.get("size_bytes")] if isinstance(size, int)]
    return {
        "entries": len(valid_entries),
        "newest": max(last_used) if last_used else None,
        "oldest": min(last_used) if last_used else None,
        "total_size_bytes": sum(sizes),
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(body, encoding="utf-8")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
