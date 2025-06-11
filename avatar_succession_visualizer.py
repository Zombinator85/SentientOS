from __future__ import annotations
from logging_config import get_log_path

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Avatar Succession Ceremony Visualizer.

Creates a Graphviz representation of avatar lineage and blessings.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

LINEAGE_LOG = get_log_path("avatar_lineage.jsonl", "AVATAR_LINEAGE_LOG")


def load_entries(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def generate_graph() -> str:
    lines = ["digraph succession {"]
    for e in load_entries(LINEAGE_LOG):
        child = e.get("avatar")
        for parent in e.get("parents", []):
            lines.append(f'    "{parent}" -> "{child}";')
    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Succession Visualizer")
    ap.add_argument("--graph", action="store_true", help="Output Graphviz DOT")
    args = ap.parse_args()
    if args.graph:
        print(generate_graph())
    else:
        print(json.dumps(load_entries(LINEAGE_LOG), indent=2))


if __name__ == "__main__":
    main()
