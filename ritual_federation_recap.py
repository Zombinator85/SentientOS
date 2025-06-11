from logging_config import get_log_path
import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import presence_pulse_api as pulse

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
CONFESSIONAL_LOG = get_log_path("confessional_log.jsonl", "CONFESSIONAL_LOG")
SUPPORT_LOG = get_log_path("support_log.jsonl")
FEDERATION_LOG = get_log_path("federation_log.jsonl")
FORGIVENESS_LOG = get_log_path("forgiveness_ledger.jsonl", "FORGIVENESS_LEDGER")
HERESY_LOG = get_log_path("heresy_log.jsonl", "HERESY_LOG")

LOGS = {
    "confession": CONFESSIONAL_LOG,
    "blessing": SUPPORT_LOG,
    "federation": FEDERATION_LOG,
    "forgiveness": FORGIVENESS_LOG,
    "heresy": HERESY_LOG,
}


def _load(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _within(entries: List[Dict[str, str]], start: datetime) -> List[Dict[str, str]]:
    res = []
    for e in entries:
        ts = e.get("timestamp")
        try:
            dt = datetime.fromisoformat(str(ts))
        except Exception:
            continue
        if dt >= start:
            res.append(e)
    return res


def generate_recap(days: int = 7, event: str = "", participant: str = "") -> str:
    start = datetime.utcnow() - timedelta(days=days)
    lines = [f"# Federation Recap last {days}d"]
    pulse_rate = pulse.pulse(days * 24 * 60)
    lines.append(f"Presence pulse: {pulse_rate:.2f}/min")
    for kind, path in LOGS.items():
        entries = _within(_load(path), start)
        if event and kind != event:
            continue
        if participant:
            entries = [e for e in entries if participant in json.dumps(e)]
        if not entries:
            continue
        lines.append(f"\n## {kind.capitalize()}")
        by_day: Dict[str, List[dict]] = {}
        for e in entries:
            day = str(e.get("timestamp", "")).split("T")[0]
            by_day.setdefault(day, []).append(e)
        for day in sorted(by_day):
            lines.append(f"\n### {day}")
            for e in by_day[day]:
                lines.append(f"* {json.dumps(e, ensure_ascii=False)}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Ritual federation recap")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--event", default="")
    ap.add_argument("--participant", default="")
    ap.add_argument("--out")
    args = ap.parse_args()
    recap = generate_recap(args.days, args.event, args.participant)
    if args.out:
        Path(args.out).write_text(recap, encoding="utf-8")
        print(args.out)
    else:
        print(recap)


if __name__ == "__main__":
    main()
