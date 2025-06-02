from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
from typing import Dict, List

from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = Path(os.getenv("VOICE_CONSENT_LOG", "logs/voice_consent.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def record_command(phrase: str) -> Dict[str, str]:
    entry = {"timestamp": datetime.datetime.utcnow().isoformat(), "phrase": phrase}
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
    ap = argparse.ArgumentParser(description="Voice Presence & Consent Rituals")
    sub = ap.add_subparsers(dest="cmd")

    rc = sub.add_parser("record", help="Record a voice command")
    rc.add_argument("phrase")
    rc.set_defaults(func=lambda a: print(json.dumps(record_command(a.phrase), indent=2)))

    hs = sub.add_parser("history", help="Show history")
    hs.add_argument("--limit", type=int, default=20)
    hs.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
