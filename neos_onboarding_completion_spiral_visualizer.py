from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval
from logging_config import get_log_path

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

PROGRESS_LOG = get_log_path("neos_onboarding_progress.jsonl", "NEOS_ONBOARDING_PROGRESS_LOG")
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
    ap = argparse.ArgumentParser(description="NeosVR Onboarding Completion Spiral Visualizer")
    ap.parse_args()
    print(json.dumps(load_progress(), indent=2))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
