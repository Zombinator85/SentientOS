from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, Tuple

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Banner: requires admin & Lumos approval."""

require_admin_banner()
require_lumos_approval()


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
    for entry in lines:
        changed = False
        if "timestamp" not in entry or "data" not in entry or not isinstance(entry.get("data"), dict):
            repaired.append(entry)
            prev = entry.get("rolling_hash", prev)
            continue
        expected = compute_hash(entry["timestamp"], entry["data"], prev)
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
        prev = expected
        if changed:
            fixed += 1
    if fixed and not check_only:
        with path.open("w", encoding="utf-8") as f:
            for e in repaired:
                f.write(json.dumps(e) + "\n")
    return prev, fixed


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Repair audit log chains")
    ap.add_argument("--logs-dir", default="logs", help="directory of logs")
    ap.add_argument("--check-only", action="store_true", help="do not modify files")
    ap.add_argument("--fix", action="store_true", help="apply repairs in place")
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
    any_mismatch = False
    for log in sorted(logs_dir.glob("*.jsonl")):
        total = sum(1 for _ in log.read_text(encoding="utf-8").splitlines() if _.strip())
        prev, fixed = repair_log(log, prev, check_only=not args.fix)
        status = "OK" if fixed == 0 else "FAIL"
        if fixed:
            any_mismatch = True
        print(f"{log.name}: {total} entries, {fixed} fixed, {status}")
    if args.check_only and any_mismatch:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
