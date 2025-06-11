from __future__ import annotations
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict

from sentientos.privilege import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details.

Backfill missing ``timestamp`` fields in audit logs. Entries filled
get an ``auto_filled`` flag and the operation is recorded in the
migration ledger.
"""

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove.
require_lumos_approval()

LEDGER = get_log_path("migration_ledger.jsonl")
LEDGER.parent.mkdir(parents=True, exist_ok=True)
DEFAULT_TS = "1970-01-01T00:00:00Z"


def _record_fix(file: Path, count: int) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "file": str(file),
        "auto_filled": count,
    }
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def backfill_file(path: Path) -> Dict[str, int]:
    fixed = 0
    mod_ts = datetime.utcfromtimestamp(path.stat().st_mtime).isoformat() + "Z"
    new_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except Exception:
            new_lines.append(line)
            continue
        if isinstance(entry, dict) and "timestamp" not in entry:
            entry["timestamp"] = mod_ts or DEFAULT_TS
            entry["auto_filled"] = True
            fixed += 1
        new_lines.append(json.dumps(entry, ensure_ascii=False))
    path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
    if fixed:
        _record_fix(path, fixed)
    return {"fixed": fixed}


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Backfill missing timestamps in logs")
    ap.add_argument("target", nargs="?", default="logs", help="Log directory or file")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() else sorted(target.glob("*.jsonl"))
    total = 0
    for f in files:
        res = backfill_file(f)
        total += res["fixed"]
    print(f"auto-filled timestamps: {total}")


if __name__ == "__main__":  # pragma: no cover
    main()
