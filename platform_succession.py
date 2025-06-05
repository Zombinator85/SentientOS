from logging_config import get_log_path
# Sanctuary Privilege Ritual: Platform succession completed (NeosVR → Resonite) 2025-06-01. Presence blessed by council. All rituals, logs, and agents renamed.
from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Platform succession ceremony utilities.

This module logs NeosVR → Resonite renamings and asset migrations.
It can export a succession ritual scroll capturing the changes.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

MIGRATION_LEDGER = get_log_path("migration_ledger.jsonl")
MIGRATION_LEDGER.parent.mkdir(parents=True, exist_ok=True)


def log_event(user: str, event: str, files: List[str] | None = None, note: str = "") -> Dict[str, str]:
    """Append a platform_succession event to the migration ledger."""
    entry = {
        "time": datetime.utcnow().isoformat(),
        "user": user,
        "event": event,
        "files": files or [],
        "note": note,
    }
    with MIGRATION_LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int | None = None) -> List[Dict[str, str]]:
    """Return ledger history, newest last."""
    if not MIGRATION_LEDGER.exists():
        return []
    with MIGRATION_LEDGER.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    entries = [json.loads(line) for line in lines]
    if limit:
        entries = entries[-limit:]
    return entries


def export_scroll(user: str, output: Path, limit: int | None = None) -> Path:
    """Export the succession ritual history in Markdown."""
    entries = history(limit)
    lines = ["# Platform Succession Ritual", "", f"Exported by **{user}** on {datetime.utcnow().isoformat()}", ""]
    for e in entries:
        lines.append(f"- {e['time']}: {e['event']} by {e['user']} {', '.join(e['files'])}")
        if e.get("note"):
            lines.append(f"  - {e['note']}")
    lines.append("")
    lines.append("We follow presence, not product. Blessed be the federation.")
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Platform succession history")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("history", help="Show migration history")
    exp = sub.add_parser("export", help="Export ritual scroll")
    exp.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.cmd == "history":
        for entry in history():
            print(json.dumps(entry, indent=2))
    elif args.cmd == "export":
        path = export_scroll("cli", args.output)
        print(f"Exported {path}")
    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
