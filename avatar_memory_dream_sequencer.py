from __future__ import annotations

"""Avatar Memory Dream Sequencer.

Generates and logs dream sequences based on memory lineage and mood.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path(os.getenv("AVATAR_DREAM_SEQUENCE_LOG", "logs/avatar_dream_sequences.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_dream(seed: str, memories: List[str], mood: str, narrative: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "seed": seed,
        "memories": memories,
        "mood": mood,
        "narrative": narrative,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_dreams() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar Memory Dream Sequencer")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log a dream sequence")
    lg.add_argument("seed")
    lg.add_argument("--memories", default="")
    lg.add_argument("--mood", default="")
    lg.add_argument("--narrative", default="")
    lg.set_defaults(
        func=lambda a: print(
            json.dumps(
                log_dream(
                    a.seed,
                    [m.strip() for m in a.memories.split(",") if m.strip()],
                    a.mood,
                    a.narrative,
                ),
                indent=2,
            )
        )
    )

    ls = sub.add_parser("list", help="List dream sequences")
    ls.set_defaults(func=lambda a: print(json.dumps(list_dreams(), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
