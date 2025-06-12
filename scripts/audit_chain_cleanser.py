from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import argparse
import json
import difflib
from typing import Iterable, Tuple, List

from audit_chain import _hash_entry


def cleanse_file(path: Path, prev: str) -> Tuple[str, List[str]]:
    """Clean one audit log file and return new prev hash and diff."""
    original = path.read_text(encoding="utf-8").splitlines()
    new_lines: List[str] = []
    changed = False

    for line in original:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except Exception:
            entry = {"_void": True, "_note": "Legacy gap sealed"}
            new_lines.append(json.dumps(entry))
            changed = True
            continue

        if not isinstance(entry, dict) or entry.get("_void") is True:
            new_lines.append(json.dumps(entry))
            continue

        timestamp = entry.get("timestamp")
        data = entry.get("data")
        current = entry.get("rolling_hash") or entry.get("hash")
        ph = entry.get("prev_hash")

        if not timestamp or not isinstance(data, dict) or not current or not ph:
            # cannot recover; mark void
            entry["_void"] = True
            entry["_note"] = "Legacy gap sealed"
            changed = True
            new_lines.append(json.dumps(entry))
            continue

        expected = _hash_entry(timestamp, data, prev)
        if ph != prev or current != expected:
            # attempt repair
            entry["prev_hash"] = prev
            entry["rolling_hash"] = expected
            entry.pop("hash", None)
            changed = True
        new_lines.append(json.dumps(entry))
        prev = expected

    if changed:
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        diff = list(
            difflib.unified_diff(original, new_lines, fromfile=str(path), tofile=str(path))
        )
    else:
        diff = []
    return prev, diff


def cleanse_directory(log_dir: Path) -> None:
    prev = "0" * 64
    for log in sorted(log_dir.rglob("*.jsonl")):
        prev, diff = cleanse_file(log, prev)
        if diff:
            print("\n".join(diff))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean audit chain gaps")
    parser.add_argument("logs", nargs="?", default="logs", help="Log directory")
    args = parser.parse_args(list(argv) if argv is not None else None)

    cleanse_directory(Path(args.logs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
