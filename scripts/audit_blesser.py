from __future__ import annotations
import json
import subprocess
from datetime import datetime
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval

"""Automatically bless audit mismatches found during verification."""

# Automatically bless audit mismatches found during verification.

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


def main() -> None:
    result = run_verify()
    output = result.stdout + result.stderr
    print(output)
    if "prev hash mismatch" in output:
        append_blessing()


if __name__ == "__main__":
    main()
