from logging_config import get_log_path
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
CONFESSIONAL_LOG = get_log_path("confessional_log.jsonl", "CONFESSIONAL_LOG")
HERESY_LOG = get_log_path("heresy_log.jsonl", "HERESY_LOG")
FORGIVENESS_LOG = get_log_path("forgiveness_ledger.jsonl", "FORGIVENESS_LEDGER")
SUPPORT_LOG = get_log_path("support_log.jsonl")


def _load(path: Path, kind: str, start: Optional[datetime], end: Optional[datetime]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            data = json.loads(line)
        except Exception:
            continue
        ts = data.get("timestamp")
        try:
            dt = datetime.fromisoformat(str(ts)) if ts else None
        except Exception:
            dt = None
        if start and dt and dt < start:
            continue
        if end and dt and dt > end:
            continue
        data["_kind"] = kind
        out.append(data)
    return out


def export_book(start: str = "", end: str = "", kind_filter: str = "") -> str:
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None
    entries = []
    entries += _load(CONFESSIONAL_LOG, "confession", start_dt, end_dt)
    entries += _load(SUPPORT_LOG, "blessing", start_dt, end_dt)
    entries += _load(HERESY_LOG, "heresy", start_dt, end_dt)
    entries += _load(FORGIVENESS_LOG, "forgiveness", start_dt, end_dt)
    if kind_filter:
        entries = [e for e in entries if e["_kind"] == kind_filter]
    entries.sort(key=lambda x: x.get("timestamp", ""))
    lines = ["# Book of Rituals"]
    current = ""
    for e in entries:
        dt = e.get("timestamp", "")
        day = dt.split("T")[0]
        if day != current:
            lines.append(f"\n## {day}")
            current = day
        kind = e.pop("_kind")
        detail = json.dumps(e, ensure_ascii=False)
        lines.append(f"* **{kind}** {detail}")
    out_path = Path("Book_of_Rituals.md")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return str(out_path)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Export ritual logs")
    p.add_argument("--start", default="")
    p.add_argument("--end", default="")
    p.add_argument("--kind", default="")
    args = p.parse_args()
    print(export_book(args.start, args.end, args.kind))
