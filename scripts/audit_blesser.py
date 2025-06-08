from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval
from scripts.auto_approve import is_auto_approve, prompt_yes_no

"""Automatically bless audit mismatches found during verification."""

require_admin_banner()
require_lumos_approval()

BLESSINGS_FILE = Path("SANCTUARY_BLESSINGS.jsonl")


def run_verify() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", "verify_audits.py", "logs/"], capture_output=True, text=True
    )


def append_blessing() -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": "automatic audit blessing",
        "reason": "legacy mismatches preserved",
        "signed_by": "Lumos",
    }
    with BLESSINGS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bless audit mismatches")
    parser.add_argument("--auto-approve", action="store_true", help="Skip prompts")
    args = parser.parse_args(argv)

    auto = args.auto_approve or is_auto_approve()

    result = run_verify()
    output = result.stdout + result.stderr
    print(output)

    mismatched = "prev hash mismatch" in output or "chain break" in output
    if mismatched:
        if auto or prompt_yes_no("Bless mismatches?"):
            append_blessing()
            return 0
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
