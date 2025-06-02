from logging_config import get_log_path
import json
from pathlib import Path
from typing import List

CONFESSION_FILE = get_log_path("confessional_log.jsonl")
BLESS_FILE = get_log_path("support_log.jsonl")


def _load(path: Path) -> List[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def report(window_minutes: int = 60) -> None:
    from datetime import datetime, timedelta

    conf = _load(CONFESSION_FILE)
    bless = _load(BLESS_FILE)
    results = []
    for c in conf:
        c_ts = datetime.fromisoformat(c.get("timestamp"))
        count = 0
        for b in bless:
            b_ts = datetime.fromisoformat(b.get("timestamp"))
            if abs((b_ts - c_ts).total_seconds()) <= window_minutes * 60:
                count += 1
        if count:
            results.append({"confession": c, "blessings": count})
    print(json.dumps(results, indent=2))


if __name__ == "__main__":  # pragma: no cover - manual
    report()
