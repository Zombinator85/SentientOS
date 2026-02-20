"""Forge Observatory artifact index and compaction helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from sentientos.contract_sentinel import ContractSentinel
from sentientos.forge_provenance import validate_chain
from sentientos.forge_merge_train import ForgeMergeTrain
from sentientos.forge_outcomes import summarize_report
from sentientos.forge_progress_contract import emit_forge_progress_contract

SCHEMA_VERSION = 2
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
    provenance = sorted((root / "glow/forge/provenance").glob("prov_*.json"), key=lambda item: item.name)
    audit_dockets = sorted((root / "glow/forge").glob("audit_docket_*.json"), key=lambda item: item.name)
    audit_doctor_reports = sorted((root / "glow/forge").glob("audit_doctor_*.json"), key=lambda item: item.name)

    queue_rows, queue_corrupt = _read_jsonl(root / QUEUE_PATH)
    receipt_rows, receipt_corrupt = _read_jsonl(root / RECEIPTS_PATH)

    sentinel_summary = ContractSentinel(repo_root=root).summary()
    merge_train = ForgeMergeTrain(repo_root=root)
    train_state = merge_train.load_state()

    latest_prs = _latest_prs(receipt_rows)
    latest_check_failures = [
        row
        for row in latest_prs
        if str(row.get("checks_overall")) in {"failure", "pending", "held_failed_checks"}
    ][:50]

    stability_doctrine = _load_json(root / "glow/contracts/stability_doctrine.json")
    raw_toolchain = stability_doctrine.get("toolchain")
    raw_vow = stability_doctrine.get("vow_artifacts")
    doctrine_toolchain: dict[str, Any] = raw_toolchain if isinstance(raw_toolchain, dict) else {}
    doctrine_vow: dict[str, Any] = raw_vow if isinstance(raw_vow, dict) else {}

    progress_trend = _progress_trend(root, reports, limit=10)
    stagnation_alert = len(progress_trend) >= 3 and all(not bool(item.get("improved", False)) for item in progress_trend[-3:])
    contract_path = root / "glow/contracts/forge_progress_baseline.json"
    progress_contract = _load_json(contract_path)
    if not progress_contract:
        progress_contract = emit_forge_progress_contract(root).to_dict()

    index: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _iso_now(),
        "latest_reports": [_load_json(path) | {"path": str(path.relative_to(root))} for path in reports[-50:]],
        "latest_dockets": [_load_json(path) | {"path": str(path.relative_to(root))} for path in dockets[-50:]],
        "latest_audit_dockets": [_load_json(path) | {"path": str(path.relative_to(root))} for path in audit_dockets[-10:]],
        "latest_audit_doctor_reports": [_load_json(path) | {"path": str(path.relative_to(root))} for path in audit_doctor_reports[-10:]],
        "latest_provenance": [_load_json(path) | {"path": str(path.relative_to(root))} for path in provenance[-50:]],
        "latest_receipts": receipt_rows[-200:],
        "latest_queue": _pending_from_rows(queue_rows, receipt_rows),
        "latest_quarantines": _latest_quarantines(root),
        "latest_prs": latest_prs,
        "latest_check_failures": latest_check_failures,
        "merge_train": {
            "enabled": merge_train.load_policy().enabled,
            "last_merged_pr": train_state.last_merged_pr,
            "entries_by_status": _train_entries_by_status(train_state.entries),
            "head": _train_head(train_state.entries),
            "entries": [_train_entry_row(item) for item in train_state.entries[-25:]],
        },
        "remote_doctrine_fetches": _latest_remote_doctrine_fetches(root),
        "last_merge_receipt": _last_merge_receipt_summary(root),
        "last_merged_doctrine_bundle_sha256": _last_merged_bundle_sha256(root),
        "env_cache": _env_cache_summary(root),
        "ci_baseline_latest": _load_json(root / "glow/contracts/ci_baseline.json") or None,
        "stability_doctrine_latest": stability_doctrine or None,
        "audit_strict_status": stability_doctrine.get("audit_strict_status") if isinstance(stability_doctrine.get("audit_strict_status"), str) else "unknown",
        "vow_artifacts_sha256": doctrine_vow.get("immutable_manifest_sha256") if isinstance(doctrine_vow.get("immutable_manifest_sha256"), str) else None,
        "verify_audits_available": bool(doctrine_toolchain.get("verify_audits_available", False)),
        "corrupt_count": {
            "queue": queue_corrupt,
            "receipts": receipt_corrupt,
            "total": queue_corrupt + receipt_corrupt,
        },
        "sentinel_enabled": sentinel_summary.get("sentinel_enabled", False),
        "sentinel_last_enqueued": sentinel_summary.get("sentinel_last_enqueued"),
        "sentinel_state": sentinel_summary.get("sentinel_state"),
        "provenance_chain": validate_chain(root),
        "progress_trend": progress_trend,
        "stagnation_alert": stagnation_alert,
        "forge_progress_contract_latest": progress_contract,
        "audit_integrity_status": {
            "baseline_ok": bool(stability_doctrine.get("baseline_integrity_ok", False)),
            "runtime_ok": bool(stability_doctrine.get("runtime_integrity_ok", False)),
            "unexpected_change_detected": bool(stability_doctrine.get("baseline_unexpected_change_detected", False)),
            "last_doctor_report_path": (str(audit_doctor_reports[-1].relative_to(root)) if audit_doctor_reports else None),
            "last_audit_docket_path": (str(audit_dockets[-1].relative_to(root)) if audit_dockets else None),
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


def _latest_prs(receipt_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in reversed(receipt_rows):
        url = row.get("publish_pr_url")
        if not isinstance(url, str) or not url:
            continue
        rows.append(
            {
                "request_id": row.get("request_id"),
                "status": row.get("status"),
                "finished_at": row.get("finished_at"),
                "pr_url": url,
                "checks_overall": row.get("publish_checks_overall") or row.get("publish_status"),
            }
        )
        if len(rows) >= 50:
            break
    return rows


def _progress_trend(root: Path, reports: list[Path], *, limit: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in reports:
        payload = _load_json(path)
        summary = summarize_report(payload)
        if summary.goal_id != "repo_green_storm":
            continue
        rows.append(
            {
                "run_id": summary.run_id,
                "created_at": summary.created_at,
                "before_failed": summary.ci_before_failed_count,
                "after_failed": summary.ci_after_failed_count,
                "progress_delta_percent": summary.progress_delta_percent,
                "improved": summary.last_progress_improved
                or (
                    summary.ci_before_failed_count is not None
                    and summary.ci_after_failed_count is not None
                    and summary.ci_after_failed_count < summary.ci_before_failed_count
                )
                or (summary.progress_delta_percent is not None and summary.progress_delta_percent > 0),
            }
        )
    return rows[-limit:]


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}



def _latest_quarantines(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted((root / "glow/forge").glob("quarantine_*.json"), key=lambda item: item.name)[-50:]:
        payload = _load_json(path)
        payload["path"] = str(path.relative_to(root))
        rows.append(payload)
    return rows

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


def _train_entries_by_status(entries: list[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        status = str(getattr(entry, "status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _train_head(entries: list[object]) -> dict[str, object] | None:
    if not entries:
        return None
    head = sorted(entries, key=lambda item: str(getattr(item, "created_at", "")))[0]
    return {
        "pr_url": getattr(head, "pr_url", None),
        "status": getattr(head, "status", None),
        "goal_id": getattr(head, "goal_id", None),
        "last_error": getattr(head, "last_error", None),
        "doctrine_source": getattr(head, "doctrine_source", None),
        "doctrine_gate_reason": getattr(head, "doctrine_gate_reason", None),
    }


def _train_entry_row(entry: object) -> dict[str, object]:
    return {
        "pr_url": getattr(entry, "pr_url", None),
        "pr_number": getattr(entry, "pr_number", None),
        "head_sha": getattr(entry, "head_sha", None),
        "status": getattr(entry, "status", None),
        "check_overall": getattr(entry, "check_overall", None),
        "last_error": getattr(entry, "last_error", None),
        "doctrine_source": getattr(entry, "doctrine_source", None),
        "doctrine_gate_reason": getattr(entry, "doctrine_gate_reason", None),
    }


def _latest_remote_doctrine_fetches(root: Path) -> list[dict[str, object]]:
    path = root / "glow/forge/remote_doctrine_fetches.jsonl"
    rows, _ = _read_jsonl(path)
    return rows[-10:]


def _last_merge_receipt_summary(root: Path) -> dict[str, object] | None:
    receipts = sorted((root / "glow/forge/receipts").glob("merge_receipt_*.json"), key=lambda item: item.name)
    if not receipts:
        return None
    payload = _load_json(receipts[-1])
    doctrine_raw = payload.get("doctrine_identity")
    doctrine: dict[str, object] = doctrine_raw if isinstance(doctrine_raw, dict) else {}
    return {
        "pr": payload.get("pr_url"),
        "sha": payload.get("head_sha"),
        "bundle_sha256": doctrine.get("bundle_sha256"),
        "source": payload.get("doctrine_source"),
    }


def _last_merged_bundle_sha256(root: Path) -> str | None:
    summary = _last_merge_receipt_summary(root)
    if not isinstance(summary, dict):
        return None
    value = summary.get("bundle_sha256")
    if not isinstance(value, str) or not value:
        return None
    return value[:16]
