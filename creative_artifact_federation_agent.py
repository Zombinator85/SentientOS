from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
from logging_config import get_log_path

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

FED_LOG = get_log_path("creative_federation.jsonl", "CREATIVE_FED_LOG")
FED_LOG.parent.mkdir(parents=True, exist_ok=True)


def send_artifact(path: Path, partner: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "artifact": str(path),
        "partner": partner,
        "action": "send",
    }
    with FED_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def receive_artifact(path: Path, partner: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "artifact": str(path),
        "partner": partner,
        "action": "receive",
    }
    with FED_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history() -> List[Dict[str, str]]:
    if not FED_LOG.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in FED_LOG.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Creative/Artifact Federation Agent")
    sub = ap.add_subparsers(dest="cmd")

    sd = sub.add_parser("send", help="Send artifact")
    sd.add_argument("path")
    sd.add_argument("partner")
    sd.set_defaults(func=lambda a: print(json.dumps(send_artifact(Path(a.path), a.partner), indent=2)))

    rv = sub.add_parser("receive", help="Receive artifact")
    rv.add_argument("path")
    rv.add_argument("partner")
    rv.set_defaults(func=lambda a: print(json.dumps(receive_artifact(Path(a.path), a.partner), indent=2)))

    ls = sub.add_parser("history", help="Show federation history")
    ls.set_defaults(func=lambda a: print(json.dumps(history(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
