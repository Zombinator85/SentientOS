from logging_config import get_log_path
import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict
from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
LOG_PATH = get_log_path("heirloom_ledger.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_state(name: str, state: str, user: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "name": name,
        "state": state,
        "user": user,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_states() -> list:
    if not LOG_PATH.exists():
        return []
    return [json.loads(l) for l in LOG_PATH.read_text(encoding="utf-8").splitlines()]


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Sacred heirloom synchronizer")
    sub = ap.add_subparsers(dest="cmd")

    upd = sub.add_parser("update", help="Update heirloom state")
    upd.add_argument("name")
    upd.add_argument("state")
    upd.add_argument("--user", default="")
    upd.set_defaults(func=lambda a: print(json.dumps(log_state(a.name, a.state, a.user), indent=2)))

    ls = sub.add_parser("list", help="List heirloom states")
    ls.set_defaults(func=lambda a: print(json.dumps(list_states(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
