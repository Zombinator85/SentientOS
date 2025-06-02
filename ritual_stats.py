from logging_config import get_log_path
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import forgiveness_ledger as fledge

COUNCIL_QUORUM = int(os.getenv("COUNCIL_QUORUM", "2"))

CONFESSIONAL_LOG = get_log_path("confessional_log.jsonl", "CONFESSIONAL_LOG")
SUPPORT_LOG = get_log_path("support_log.jsonl")


def _load(path: Path) -> List[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def stats(days: int = 7) -> Dict[str, float]:
    now = datetime.utcnow()
    start = now - timedelta(days=days)
    def _dt(val: str) -> datetime:
        try:
            return datetime.fromisoformat(val)
        except Exception:
            return start

    conf = [e for e in _load(CONFESSIONAL_LOG) if _dt(e.get("timestamp", now.isoformat())) >= start]
    forgive = [e for e in _load(fledge.LEDGER_PATH) if e.get("event") != "council_vote" and _dt(e.get("timestamp", now.isoformat())) >= start]
    bless = [e for e in _load(SUPPORT_LOG) if _dt(e.get("timestamp", now.isoformat())) >= start]
    conf_per_week = len(conf)
    forgiveness_rate = (len(forgive) / conf_per_week) if conf_per_week else 0.0
    blessing_freq = len(bless) / days
    avg_council_time = 0.0
    durations = []
    for c in conf:
        if not c.get("council_required"):
            continue
        ts = c.get("timestamp")
        votes = [v for v in fledge.council_votes(ts) if datetime.fromisoformat(v["timestamp"]) >= start]
        approvals = [v for v in votes if v.get("decision") == "approve"]
        if len(approvals) >= COUNCIL_QUORUM:
            times = sorted(datetime.fromisoformat(v["timestamp"]) for v in approvals)
            durations.append((times[-1] - datetime.fromisoformat(ts)).total_seconds())
    if durations:
        avg_council_time = sum(durations) / len(durations)
    return {
        "confessions": conf_per_week,
        "forgiveness_rate": forgiveness_rate,
        "blessing_frequency": blessing_freq,
        "avg_council_seconds": avg_council_time,
    }


if __name__ == "__main__":
    print(json.dumps(stats(), indent=2))
