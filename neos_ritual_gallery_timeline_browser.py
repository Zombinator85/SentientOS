from __future__ import annotations
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

LOG_PATH = get_log_path("neos_ritual_gallery_timeline.jsonl", "NEOS_RITUAL_GALLERY_TIMELINE_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def list_events(agent: str = "", artifact: str = "") -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except Exception:
            continue
        if agent and event.get("agent") != agent:
            continue
        if artifact and event.get("artifact") != artifact:
            continue
        out.append(event)
    return out


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Ritual Gallery Timeline Browser")
    ap.add_argument("--agent", default="", help="Filter by agent")
    ap.add_argument("--artifact", default="", help="Filter by artifact")
    args = ap.parse_args()
    events = list_events(args.agent, args.artifact)
    print(json.dumps(events, indent=2))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
