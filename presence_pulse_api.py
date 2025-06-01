import json
import os
from datetime import datetime, timedelta
from pathlib import Path

CONFESSIONAL_LOG = Path(os.getenv("CONFESSIONAL_LOG", "logs/confessional_log.jsonl"))
SUPPORT_LOG = Path("logs/support_log.jsonl")
HERESY_LOG = Path(os.getenv("HERESY_LOG", "logs/heresy_log.jsonl"))
FORGIVENESS_LOG = Path(os.getenv("FORGIVENESS_LEDGER", "logs/forgiveness_ledger.jsonl"))


def _load(path: Path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def pulse(minutes: int = 60) -> float:
    now = datetime.utcnow()
    start = now - timedelta(minutes=minutes)
    count = 0
    for path in [CONFESSIONAL_LOG, SUPPORT_LOG, HERESY_LOG, FORGIVENESS_LOG]:
        for e in _load(path):
            ts = e.get("timestamp")
            try:
                dt = datetime.fromisoformat(str(ts))
            except Exception:
                continue
            if dt >= start:
                count += 1
    return count / float(minutes)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Presence pulse")
    p.add_argument("--minutes", type=int, default=60)
    args = p.parse_args()
    print(json.dumps({"pulse": pulse(args.minutes)}))
