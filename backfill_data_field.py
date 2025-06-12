"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import argparse
import json
from datetime import datetime
from pathlib import Path

from logging_config import get_log_path


LEDGER = get_log_path("migration_ledger.jsonl")
LEDGER.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_NOTE = (
    "Legacy log missing data field. Auto-filled for schema compliance."
)


def _record_fix(path: Path, count: int) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "log_file": path.name,
        "action": f"Auto-filled missing data field ({count})",
        "data": {
            "note": DEFAULT_NOTE,
            "auto_filled": True,
        },
    }
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def backfill_file(path: Path) -> int:
    fixed = 0
    new_lines = []
    buffer = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        buffer += raw.strip()
        try:
            entry = json.loads(buffer)
            buffer = ""
        except json.JSONDecodeError:
            buffer += " "
            continue
        if isinstance(entry, dict) and "data" not in entry:
            entry["data"] = {
                "note": DEFAULT_NOTE,
                "auto_filled": True,
                "original_entry": str({k: entry[k] for k in entry if k != "data"}),
            }
            fixed += 1
        new_lines.append(json.dumps(entry, ensure_ascii=False))
    if buffer.strip():
        try:
            entry = json.loads(buffer)
            if isinstance(entry, dict) and "data" not in entry:
                entry["data"] = {
                    "note": DEFAULT_NOTE,
                    "auto_filled": True,
                    "original_entry": str({k: entry[k] for k in entry if k != "data"}),
                }
                fixed += 1
            new_lines.append(json.dumps(entry, ensure_ascii=False))
        except Exception:
            new_lines.append(buffer)
    path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
    if fixed:
        _record_fix(path, fixed)
    return fixed


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Backfill missing data fields in logs")
    ap.add_argument("target", nargs="?", default="logs", help="Log directory or file")
    args = ap.parse_args()
    target = Path(args.target)
    files = [target] if target.is_file() else sorted(target.glob("*.jsonl"))
    total = 0
    for f in files:
        total += backfill_file(f)
    print(f"auto-filled data fields: {total}")


if __name__ == "__main__":  # pragma: no cover
    main()
