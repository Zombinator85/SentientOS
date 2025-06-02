from __future__ import annotations

"""NeosVR Privilege Audit Regression Tester."""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from log_utils import append_json, read_json

LOG_PATH = Path(os.getenv("NEOS_PRIVILEGE_TEST_LOG", "logs/neos_privilege_tests.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_test(name: str, result: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "result": result,
    }
    append_json(LOG_PATH, entry)
    return entry


def list_tests() -> List[Dict[str, str]]:
    return read_json(LOG_PATH)


def run_daemon(interval: float) -> None:
    while True:
        log_test("heartbeat", "ok")
        time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Privilege Regression Tester")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log test result")
    lg.add_argument("name")
    lg.add_argument("result")
    lg.set_defaults(func=lambda a: print(json.dumps(log_test(a.name, a.result), indent=2)))

    ls = sub.add_parser("list", help="List tests")
    ls.set_defaults(func=lambda a: print(json.dumps(list_tests(), indent=2)))

    rn = sub.add_parser("run", help="Run daemon")
    rn.add_argument("--interval", type=float, default=60.0)
    rn.set_defaults(func=lambda a: run_daemon(a.interval))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
