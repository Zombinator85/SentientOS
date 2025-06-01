import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import presence_pulse_api as pulse
import ledger


def digest(days: int = 1) -> dict:
    start = datetime.utcnow() - timedelta(days=days)
    sup = ledger.summarize_log(Path("logs/support_log.jsonl"), limit=100)
    conf = ledger.summarize_log(Path("logs/confessional_log.jsonl"), limit=100)
    fed = ledger.summarize_log(Path("logs/federation_log.jsonl"), limit=100)
    forgiven = ledger.summarize_log(Path("logs/forgiveness_ledger.jsonl"), limit=100)
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
