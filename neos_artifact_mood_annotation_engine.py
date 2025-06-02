from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

LOG_PATH = Path(os.getenv("NEOS_ARTIFACT_MOOD_LOG", "logs/neos_artifact_mood.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def annotate_artifact(artifact: str, mood: str, teaching: str = "") -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "artifact": artifact,
        "mood": mood,
        "teaching": teaching,
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

def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Artifact Mood Annotation Engine")
    sub = ap.add_subparsers(dest="cmd")

    an = sub.add_parser("annotate", help="Annotate artifact with mood")
    an.add_argument("artifact")
    an.add_argument("mood")
    an.add_argument("--teaching", default="")
    an.set_defaults(func=lambda a: print(json.dumps(annotate_artifact(a.artifact, a.mood, a.teaching), indent=2)))

    hist = sub.add_parser("history", help="Show annotation history")
    hist.add_argument("--limit", type=int, default=20)
    hist.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
