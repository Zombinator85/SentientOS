from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from sentientos.audit_chain_gate import verify_audit_chain
from sentientos.event_stream import record_forge_event


def _now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rebuild_receipts_index(repo_root: Path) -> dict[str, Any]:
    receipts_dir = repo_root / "glow/forge/receipts"
    index_path = receipts_dir / "receipts_index.jsonl"
    before = _sha(index_path)
    rows: list[dict[str, object]] = []
    prev_hash: str | None = None
    for receipt in sorted(receipts_dir.glob("merge_receipt_*.json"), key=lambda item: item.name):
        try:
            payload = json.loads(receipt.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        rows.append(
            {
                "receipt_id": payload.get("receipt_id"),
                "created_at": payload.get("created_at"),
                "receipt_hash": payload.get("receipt_hash"),
                "prev_receipt_hash": payload.get("prev_receipt_hash", prev_hash),
                "pr_number": payload.get("pr_number"),
                "head_sha": payload.get("head_sha"),
            }
        )
        rh = payload.get("receipt_hash")
        prev_hash = rh if isinstance(rh, str) else prev_hash
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    return {
        "kind": "repair_index_only",
        "path": str(index_path.relative_to(repo_root)),
        "sha_before": before,
        "sha_after": _sha(index_path),
        "row_count": len(rows),
    }


def _truncate_after_break(repo_root: Path, break_path: str, break_line: int) -> dict[str, Any]:
    target = repo_root / break_path
    before = _sha(target)
    lines = target.read_text(encoding="utf-8").splitlines()
    kept = lines[: max(0, break_line - 1)]
    body = "\n".join(kept)
    if kept:
        body += "\n"
    target.write_text(body, encoding="utf-8")
    return {
        "kind": "truncate_after_break",
        "path": break_path,
        "line_kept": len(kept),
        "sha_before": before,
        "sha_after": _sha(target),
    }


def _write_report(repo_root: Path, payload: dict[str, Any]) -> str:
    reports = repo_root / "glow/forge/audit_reports"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / f"audit_doctor_{_now_tag()}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path.relative_to(repo_root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit chain doctor (deterministic, explicit repairs only)")
    parser.add_argument("--diagnose-only", action="store_true", help="only diagnose")
    parser.add_argument("--repair-index-only", action="store_true", help="rebuild derived receipts index")
    parser.add_argument("--truncate-after-break", action="store_true", help="truncate broken file after first break")
    parser.add_argument("--rebuild-missing-prev-links", action="store_true", help="refused unless enough metadata exists")
    parser.add_argument("--i-understand", action="store_true", help="required with truncate-after-break")
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    verification = verify_audit_chain(root)
    actions: list[dict[str, Any]] = []
    refused: list[str] = []

    if args.repair_index_only:
        actions.append(_rebuild_receipts_index(root))

    if args.rebuild_missing_prev_links:
        refused.append("rebuild_missing_prev_links_refused: insufficient deterministic source metadata")

    if args.truncate_after_break:
        if not args.i_understand:
            refused.append("truncate_after_break_refused: requires --i-understand")
        elif verification.first_break is None:
            refused.append("truncate_after_break_refused: no break detected")
        else:
            actions.append(_truncate_after_break(root, verification.first_break.path, verification.first_break.line_number))

    after = verify_audit_chain(root)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "created_at": _iso_now(),
        "status": "repaired" if actions else ("needs_decision" if refused else "diagnosed"),
        "before": verification.to_dict(),
        "after": after.to_dict(),
        "actions": actions,
        "refused": refused,
    }
    report = _write_report(root, payload)
    payload["report_path"] = report
    print(json.dumps(payload, sort_keys=True))
    try:
        record_forge_event({"event": "audit_chain_doctor", "level": "info", "status": payload["status"], "report_path": report})
    except Exception:
        pass
    return 0 if after.ok or not args.truncate_after_break else 1


if __name__ == "__main__":
    raise SystemExit(main())
