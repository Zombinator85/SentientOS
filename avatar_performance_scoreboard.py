"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

"""Ritual Avatar Performance Scoreboard."""

from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_performance.jsonl", "AVATAR_PERFORMANCE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_metric(avatar: str, metric: str, value: int) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "metric": metric,
        "value": value,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def aggregate_scores() -> Dict[str, Dict[str, int]]:
    scores: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    if not LOG_PATH.exists():
        return {}
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        scores[e["avatar"]][e["metric"]] += int(e.get("value", 0))
    return scores


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Performance Scoreboard")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log a performance metric")
    lg.add_argument("avatar")
    lg.add_argument("metric")
    lg.add_argument("value", type=int)
    lg.set_defaults(func=lambda a: print(json.dumps(log_metric(a.avatar, a.metric, a.value), indent=2)))

    ag = sub.add_parser("aggregate", help="Show aggregated scores")
    ag.set_defaults(func=lambda a: print(json.dumps(aggregate_scores(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
