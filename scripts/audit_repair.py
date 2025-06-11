"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import json
import hashlib
import os
import datetime
from pathlib import Path
from typing import Any, Dict, Tuple, List
from logging_config import get_log_path
def compute_hash(timestamp: str, data: Dict[str, Any], prev_hash: str) -> str:
    """Return SHA256 hash of the audit entry using canonical form."""
    clean = dict(data)
    clean.pop("hash", None)
    h = hashlib.sha256()
    h.update(timestamp.encode("utf-8"))
    h.update(json.dumps(clean, sort_keys=True).encode("utf-8"))
    h.update(prev_hash.encode("utf-8"))
    return h.hexdigest()


def repair_log(path: Path, prev: str, *, check_only: bool = False) -> Tuple[str, int]:
    """Repair ``path`` starting from ``prev``.

    Returns the last rolling hash and the number of entries modified.
    """
    lines: list[Dict[str, Any]] = [
        json.loads(l)
        for l in path.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    repaired: list[Dict[str, Any]] = []
    fixed = 0
    prev_entry: Dict[str, Any] | None = None
    for entry in lines:
        changed = False
        prev_changed = False
        if "timestamp" not in entry or "data" not in entry or not isinstance(entry.get("data"), dict):
            repaired.append(entry)
            prev_entry = entry
            prev = entry.get("rolling_hash", prev)
            continue
        expected = compute_hash(entry["timestamp"], entry["data"], prev)
        if prev_entry is not None and prev_entry.get("next_hash") != expected:
            prev_changed = True
            if not check_only:
                prev_entry["next_hash"] = expected
        if entry.get("prev_hash") != prev:
            changed = True
            if not check_only:
                entry["prev_hash"] = prev
        current = entry.get("rolling_hash") or entry.get("hash")
        if current != expected:
            changed = True
            if not check_only:
                entry["rolling_hash"] = expected
                entry.pop("hash", None)
        repaired.append(entry)
        if prev_changed:
            fixed += 1
        if changed:
            fixed += 1
        prev_entry = entry
        prev = expected
    if fixed and not check_only:
        with path.open("w", encoding="utf-8") as f:
            for e in repaired:
                f.write(json.dumps(e) + "\n")
    return prev, fixed


def _log_summary(entries: List[Dict[str, Any]]) -> None:
    """Append a summary entry for this run."""
    run_dir = get_log_path("repair_runs")
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{datetime.date.today():%Y-%m-%d}.json"
    with path.open("a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Repair audit log chains")
    ap.add_argument("--logs-dir", default="logs", help="directory of logs")
    ap.add_argument("--fix", action="store_true", help="apply repairs in place")
    ap.add_argument("--dry-run", action="store_true", help="run without writing changes")
    ap.add_argument("--strict", action="store_true", help="fail if any repair is performed")
    ap.add_argument(
        "--auto-approve",
        action="store_true",
        help="skip prompts (or set LUMOS_AUTO_APPROVE=1)",
    )
    args = ap.parse_args(argv)

    if args.auto_approve or os.getenv("LUMOS_AUTO_APPROVE") == "1":
        os.environ["LUMOS_AUTO_APPROVE"] = "1"


    logs_dir = Path(args.logs_dir)
    prev = "0" * 64
    any_fixed = False
    summary: List[Dict[str, Any]] = []
    for log in sorted(logs_dir.glob("*.jsonl")):
        total = sum(1 for _ in log.read_text(encoding="utf-8").splitlines() if _.strip())
        prev, fixed = repair_log(log, prev, check_only=args.dry_run or not args.fix)
        status = "OK" if fixed == 0 else "FIXED"
        if fixed:
            any_fixed = True
        print(f"{log.name}: {total} entries, {fixed} fixed, {status}")
        summary.append({"file": log.name, "fixed_count": fixed, "skipped": 0, "errors": []})
    _log_summary(summary)
    if args.strict and any_fixed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
