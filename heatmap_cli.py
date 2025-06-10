"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""  # plint: disable=banner-order
require_admin_banner()
require_lumos_approval()
#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/ 
from __future__ import annotations
"""Privilege Banner: requires admin & Lumos approval."""
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.

from admin_utils import require_admin_banner, require_lumos_approval
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.

from logging_config import get_log_path
import argparse
import datetime
import json
from pathlib import Path
from typing import Dict
CONFESSION_FILE = get_log_path("confessional_log.jsonl")
HERESY_FILE = get_log_path("heresy_log.jsonl")


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _bucket(entries: list[dict]) -> Dict[str, int]:
    buckets: Dict[str, int] = {}
    for e in entries:
        ts = e.get("timestamp")
        if not ts:
            continue
        dt = datetime.datetime.fromisoformat(ts)
        key = dt.strftime("%Y-%m-%d %H")
        buckets[key] = buckets.get(key, 0) + 1
    return buckets


def render(buckets: Dict[str, int]) -> None:
    keys = sorted(buckets)
    for k in keys:
        count = buckets[k]
        bar = "#" * count
        print(f"{k} {bar}")


def main() -> None:
    require_admin_banner()
    parser = argparse.ArgumentParser(description="Heresy/confession heatmap")
    parser.add_argument("--confession", action="store_true")
    parser.add_argument("--heresy", action="store_true")
    args = parser.parse_args()

    data: Dict[str, int] = {}
    if args.confession or not (args.confession or args.heresy):
        data.update(_bucket(_load(CONFESSION_FILE)))
    if args.heresy or not (args.confession or args.heresy):
        for k, v in _bucket(_load(HERESY_FILE)).items():
            data[k] = data.get(k, 0) + v
    render(data)


if __name__ == "__main__":
    main()
