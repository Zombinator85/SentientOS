"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from logging_config import get_log_path
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
import presence_pulse_api as pulse
import ledger
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
def digest(days: int = 1) -> dict:
    start = datetime.utcnow() - timedelta(days=days)
    sup = ledger.summarize_log(get_log_path("support_log.jsonl"), limit=100)
    conf = ledger.summarize_log(get_log_path("confessional_log.jsonl"), limit=100)
    fed = ledger.summarize_log(get_log_path("federation_log.jsonl"), limit=100)
    forgiven = ledger.summarize_log(get_log_path("forgiveness_ledger.jsonl"), limit=100)
    pulse_rate = pulse.pulse(days * 24 * 60)
    return {
        "pulse": pulse_rate,
        "support": sup["count"],
        "confessions": conf["count"],
        "federation": fed["count"],
        "forgiveness": forgiven["count"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Ritual recap digest")
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--out")
    args = ap.parse_args()
    d = digest(args.days)
    text = json.dumps(d, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(args.out)
    else:
        print(text)


if __name__ == "__main__":
    main()
