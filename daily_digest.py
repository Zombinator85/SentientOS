"""Daily digest utility.

This script summarizes recent log activity and emotion changes. It is
expected to be scheduled (e.g. via cron) every 24 hours. Older log
fragments can optionally be pruned to keep disk usage reasonable.

Integration Notes: schedule ``run_digest`` via cron or a task runner. Dashboards can read ``logs/daily_digest.jsonl`` for a summary feed.
"""

from __future__ import annotations
import datetime as _dt
import json
import os
from pathlib import Path
from logging_config import get_log_path
from typing import Dict, List

DIGEST_LOG = get_log_path("daily_digest.jsonl", "DAILY_DIGEST_LOG")
DIGEST_LOG.parent.mkdir(parents=True, exist_ok=True)
RETENTION_DAYS = int(os.getenv("DIGEST_KEEP_DAYS", "7"))


def _parse_ts(ts: str) -> _dt.datetime:
    try:
        return _dt.datetime.fromisoformat(ts)
    except Exception:
        return _dt.datetime.utcnow()


def _summarize_file(path: Path, since: _dt.datetime) -> int:
    count = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    ts = _parse_ts(str(data.get("timestamp")))
                    if ts >= since:
                        count += 1
                except Exception:
                    continue
    except FileNotFoundError:
        return 0
    return count


def run_digest(period_hours: int = 24) -> Dict[str, int]:
    cutoff = _dt.datetime.utcnow() - _dt.timedelta(hours=period_hours)
    logs_dir = get_log_path("")
    summary: Dict[str, int] = {}
    for fp in logs_dir.rglob("*.jsonl"):
        if fp.name == DIGEST_LOG.name:
            continue
        summary[str(fp)] = _summarize_file(fp, cutoff)
    entry = {"timestamp": _dt.datetime.utcnow().isoformat(), "summary": summary}
    with open(DIGEST_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    _prune_old(logs_dir)
    return summary


def _prune_old(root: Path) -> None:
    cutoff = _dt.datetime.utcnow() - _dt.timedelta(days=RETENTION_DAYS)
    for fp in root.rglob("*.jsonl"):
        try:
            lines = [
                l
                for l in fp.read_text(encoding="utf-8").splitlines()
                if l.strip()
            ]
        except Exception:
            continue
        keep: List[str] = []
        for line in lines:
            try:
                data = json.loads(line)
                ts = _parse_ts(str(data.get("timestamp")))
                if ts >= cutoff:
                    keep.append(line)
            except Exception:
                keep.append(line)
        fp.write_text("\n".join(keep) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - manual execution
    run_digest()
