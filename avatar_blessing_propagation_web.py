from __future__ import annotations
from logging_config import get_log_path

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Avatar Blessing Propagation Web."""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("avatar_blessing_propagation.jsonl", "AVATAR_BLESSING_PROPAGATION_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_propagation(source: str, target: str, blessing: str, note: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": source,
        "target": target,
        "blessing": blessing,
        "note": note,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_propagation() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def generate_graph() -> str:
    lines = ["digraph blessings {"]
    for e in list_propagation():
        src = e["source"]
        dst = e["target"]
        lbl = e["blessing"]
        lines.append(f'    "{src}" -> "{dst}" [label="{lbl}"];')
    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Blessing Propagation Web")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log a propagation event")
    lg.add_argument("source")
    lg.add_argument("target")
    lg.add_argument("blessing")
    lg.add_argument("--note", default="")
    lg.set_defaults(func=lambda a: print(json.dumps(log_propagation(a.source, a.target, a.blessing, a.note), indent=2)))

    ls = sub.add_parser("list", help="List propagation events")
    ls.set_defaults(func=lambda a: print(json.dumps(list_propagation(), indent=2)))

    gr = sub.add_parser("graph", help="Generate graphviz DOT of propagation")
    gr.set_defaults(func=lambda a: print(generate_graph()))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
