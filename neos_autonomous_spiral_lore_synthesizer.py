from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path(os.getenv("NEOS_SPIRAL_LORE_LOG", "logs/neos_spiral_lore.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def synthesize(source: str, text: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": source,
        "text": text,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(
        description="NeosVR Autonomous Spiral Lore Synthesizer"
    )
    sub = ap.add_subparsers(dest="cmd")

    syn = sub.add_parser("synthesize", help="Generate and log lore")
    syn.add_argument("source")
    syn.add_argument("text")
    syn.set_defaults(
        func=lambda a: print(json.dumps(synthesize(a.source, a.text), indent=2))
    )

    hist = sub.add_parser("history", help="Show lore history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
