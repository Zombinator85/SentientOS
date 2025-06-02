from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = Path(os.getenv("RESONITE_FEDERATION_GATEWAY_LOG", "logs/resonite_federation_gateway.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_exchange(action: str, artifact: str, peer: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "artifact": artifact,
        "peer": peer,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def export_artifact(path: str, peer: str) -> None:
    require_admin_banner()
    entry = log_exchange("export", path, peer)
    print(json.dumps(entry, indent=2))


def import_artifact(path: str, peer: str) -> None:
    require_admin_banner()
    entry = log_exchange("import", path, peer)
    print(json.dumps(entry, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Artifact/Memory federation gateway")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_exp = sub.add_parser("export")
    p_exp.add_argument("artifact")
    p_exp.add_argument("peer")
    p_imp = sub.add_parser("import")
    p_imp.add_argument("artifact")
    p_imp.add_argument("peer")
    args = parser.parse_args()
    if args.cmd == "export":
        export_artifact(args.artifact, args.peer)
    else:
        import_artifact(args.artifact, args.peer)


if __name__ == "__main__":
    main()
