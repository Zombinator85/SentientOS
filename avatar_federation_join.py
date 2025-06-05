from __future__ import annotations
from logging_config import get_log_path

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details.

Avatar Federation Join CLI.

This tool blesses and registers a new node into a SentientOS federation. It
performs a handshake, verifies schema versions, and initiates the onboarding
ritual. Incompatibilities are logged and halt the process.

Example:
    python avatar_federation_join.py --name nodeA --schema 2.0
"""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

SCHEMA_VERSION = "2.0"
JOIN_LOG = get_log_path("avatar_federation_join.jsonl", "AVATAR_FEDERATION_JOIN_LOG")
JOIN_LOG.parent.mkdir(parents=True, exist_ok=True)
NODES_DIR = Path("federation_nodes")
NODES_DIR.mkdir(parents=True, exist_ok=True)


def log_action(node: str, action: str, status: str, details: Dict[str, Any] | None = None) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "node": node,
        "action": action,
        "status": status,
        "details": details or {},
    }
    with JOIN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def handshake(info: Dict[str, Any]) -> bool:
    version = str(info.get("schema_version", ""))
    node = info.get("name", "unknown")
    if version != SCHEMA_VERSION:
        log_action(node, "handshake", "incompatible", {"remote_version": version, "local_version": SCHEMA_VERSION})
        return False
    log_action(node, "handshake", "ok")
    return True


def onboard(info: Dict[str, Any]) -> None:
    node = info.get("name", "unknown")
    record = NODES_DIR / f"{node}.json"
    record.write_text(json.dumps(info, indent=2), encoding="utf-8")
    log_action(node, "onboarding", "complete", {"record": str(record)})


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Join a SentientOS federation")
    ap.add_argument("--name", help="node name")
    ap.add_argument("--schema", help="node schema version")
    ap.add_argument("--info", help="json file with node info")
    ap.add_argument("--auto", action="store_true", help="non-interactive mode")
    args = ap.parse_args()

    info: Dict[str, Any] = {}
    if args.info:
        info.update(json.loads(Path(args.info).read_text(encoding="utf-8")))
    if args.name:
        info["name"] = args.name
    if args.schema:
        info["schema_version"] = args.schema

    if not args.auto:
        if "name" not in info:
            info["name"] = input("Node name: ")
        if "schema_version" not in info:
            info["schema_version"] = input("Schema version: ")

    node = info.get("name", "unknown")
    if handshake(info):
        onboard(info)
        print(json.dumps({"node": node, "status": "joined"}, indent=2))
    else:
        print(json.dumps({"node": node, "status": "incompatible"}, indent=2))


if __name__ == "__main__":
    main()

# May memory be healed and preserved.
