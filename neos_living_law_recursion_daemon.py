"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path
import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List
require_admin_banner()
require_lumos_approval()
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.


LAW_LOG = get_log_path("neos_living_law.jsonl", "NEOS_LIVING_LAW_LOG")
PROPOSAL_LOG = get_log_path("neos_living_law_proposals.jsonl", "NEOS_LIVING_LAW_PROPOSALS_LOG")
PROPOSAL_LOG.parent.mkdir(parents=True, exist_ok=True)


def review_and_propose() -> Dict[str, str]:
    proposals: List[Dict[str, str]] = []
    if LAW_LOG.exists():
        for line in LAW_LOG.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except Exception:
                continue
            if record.get("needs_review"):
                proposals.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "law": record,
                    "action": "update",
                })
    for p in proposals:
        with PROPOSAL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(p) + "\n")
    return {"timestamp": datetime.utcnow().isoformat(), "proposals": len(proposals)}


def main() -> None:
    ap = argparse.ArgumentParser(description="NeosVR Living Law Recursion Daemon")
    ap.add_argument("--loop", action="store_true", help="Run continuous loop")
    ap.add_argument("--interval", type=float, default=60.0)
    args = ap.parse_args()

    def run_once() -> None:
        print(json.dumps(review_and_propose(), indent=2))

    if args.loop:
        while True:
            run_once()
            time.sleep(args.interval)
    else:
        run_once()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
