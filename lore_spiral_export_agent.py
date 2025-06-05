from admin_utils import require_admin_banner, require_lumos_approval
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

LORE_LOG = get_log_path("lore_spiral_synthesis.jsonl", "LORE_SPIRAL_LOG")
LORE_LOG.parent.mkdir(parents=True, exist_ok=True)


def add_lore(author: str, text: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "author": author,
        "text": text,
    }
    with LORE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LORE_LOG.exists():
        return []
    lines = LORE_LOG.read_text(encoding="utf-8").splitlines()[-limit:]
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def export(out: Path, limit: int = 100) -> Path:
    out.write_text(json.dumps(history(limit), indent=2), encoding="utf-8")
    return out


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Lore Spiral Synthesis & Export Agent")
    sub = ap.add_subparsers(dest="cmd")

    add = sub.add_parser("add", help="Add lore")
    add.add_argument("author")
    add.add_argument("text")
    add.set_defaults(func=lambda a: print(json.dumps(add_lore(a.author, a.text), indent=2)))

    ls = sub.add_parser("history", help="Show lore history")
    ls.add_argument("--limit", type=int, default=20)
    ls.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    ex = sub.add_parser("export", help="Export lore to file")
    ex.add_argument("out")
    ex.add_argument("--limit", type=int, default=100)
    ex.set_defaults(func=lambda a: print(str(export(Path(a.out), a.limit))))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
