from __future__ import annotations

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

PROGRESS_LOG = Path(os.getenv("NEOS_ONBOARDING_PROGRESS_LOG", "logs/neos_onboarding_progress.jsonl"))
PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)


def load_progress() -> List[Dict[str, str]]:
    if not PROGRESS_LOG.exists():
        return []
    out: List[Dict[str, str]] = []
    for ln in PROGRESS_LOG.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="NeosVR Onboarding Completion Spiral Visualizer")
    ap.parse_args()
    print(json.dumps(load_progress(), indent=2))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
