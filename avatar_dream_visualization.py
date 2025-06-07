"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

from admin_utils import require_admin_banner, require_lumos_approval

from __future__ import annotations
from logging_config import get_log_path
"""Avatar Dream/Festival Visualization.

Visualizes active/inactive avatar dreams, festival ceremonies, or mass rituals.
Outputs Markdown or simple HTML.
"""

import argparse
import json
import os
from pathlib import Path
from typing import List, Dict

DREAM_LOG = get_log_path("avatar_dreams.jsonl", "AVATAR_DREAM_LOG")
CEREMONY_LOG = get_log_path("avatar_ceremony_log.jsonl", "AVATAR_CEREMONY_LOG")


def load_events(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def generate_report(html: bool = False) -> str:
    dreams = load_events(DREAM_LOG)
    ceremonies = load_events(CEREMONY_LOG)
    lines = ["# Avatar Dreams & Festivals"]
    lines.append("## Dreams")
    for d in dreams:
        lines.append(f"* {d.get('seed', '')} - {d.get('info', {}).get('note', '')}")
    lines.append("\n## Ceremonies")
    for c in ceremonies:
        lines.append(f"* {c.get('name')} on {c.get('date')} ({c.get('type')})")
    md = "\n".join(lines)
    return md if not html else md.replace("\n", "<br>\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Dream/Festival Visualization")
    ap.add_argument("--html", action="store_true")
    args = ap.parse_args()
    print(generate_report(html=args.html))


if __name__ == "__main__":
    main()
