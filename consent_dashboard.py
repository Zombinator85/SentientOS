"""Consent Dashboard & Ritual CLI

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from admin_utils import require_admin_banner

CONFIG_PATH = Path(os.getenv("CONSENT_CONFIG", "config/consent.json"))
LOG_PATH = Path(os.getenv("CONSENT_LOG", "logs/consent_log.jsonl"))
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_consent() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def save_consent(data: Dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


def set_consent(name: str, value: bool) -> Dict[str, Any]:
    data = load_consent()
    data[name] = {"value": value, "timestamp": datetime.utcnow().isoformat()}
    save_consent(data)
    entry = {"timestamp": datetime.utcnow().isoformat(), "consent": name, "value": value}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def cli() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Consent dashboard")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("set")
    s.add_argument("name")
    s.add_argument("value", choices=["true", "false"])
    g = sub.add_parser("get")
    g.add_argument("name")
    args = ap.parse_args()

    if args.cmd == "set":
        val = args.value.lower() == "true"
        entry = set_consent(args.name, val)
        print(json.dumps(entry, indent=2))
    elif args.cmd == "get":
        print(json.dumps(load_consent().get(args.name), indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover
    cli()
