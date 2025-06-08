from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Banner: requires admin & Lumos approval."""

require_admin_banner()
require_lumos_approval()


def compute_hash(timestamp: str, data: dict, prev_hash: str) -> str:
    """Return SHA256 hash of the audit entry."""
    h = hashlib.sha256()
    h.update(timestamp.encode("utf-8"))
    h.update(json.dumps(data, sort_keys=True).encode("utf-8"))
    h.update(prev_hash.encode("utf-8"))
    return h.hexdigest()


def repair_log(path: Path, prev: str) -> str:
    """Repair ``path`` starting from ``prev`` and return last hash."""
    lines = [
        json.loads(l)
        for l in path.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    repaired = []
    for entry in lines:
        if entry.get("prev_hash") != prev:
            entry["prev_hash"] = prev
        digest = compute_hash(entry["timestamp"], entry["data"], prev)
        entry["rolling_hash"] = digest
        repaired.append(entry)
        prev = digest
    with path.open("w", encoding="utf-8") as f:
        for e in repaired:
            f.write(json.dumps(e) + "\n")
    return prev


def main() -> None:
    logs_dir = Path("logs")
    prev = "0" * 64
    for log in sorted(logs_dir.glob("*.jsonl")):
        prev = repair_log(log, prev)
    print("\N{WHITE HEAVY CHECK MARK} All logs repaired.")


if __name__ == "__main__":
    main()
