import datetime
import json
from pathlib import Path
from typing import List, Dict

from logging_config import get_log_path

import confessional_log as clog

HERESY_LOG = get_log_path("heresy_log.jsonl")
BLESS_LOG = get_log_path("support_log.jsonl")
REPORT_PATH = get_log_path("ritual_sabbath.md")


def _load_jsonl(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def compile_report(days: int = 7) -> None:
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    confessions = [
        c for c in clog.tail(1000)
        if c.get("timestamp", "") >= cutoff.isoformat()
    ]
    heresy = [
        h for h in _load_jsonl(HERESY_LOG)
        if h.get("timestamp", "") >= cutoff.isoformat()
    ]
    blessings = [
        b for b in _load_jsonl(BLESS_LOG)
        if b.get("timestamp", "") >= cutoff.isoformat()
    ]
    lines = ["# Sabbath Reflection", ""]
    lines.append(f"Confessions: {len(confessions)}")
    lines.append(f"Unresolved heresies: {len(heresy)}")
    lines.append(f"Blessings: {len(blessings)}")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {REPORT_PATH}")


if __name__ == "__main__":  # pragma: no cover - manual use
    compile_report()
