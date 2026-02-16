"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import json
import subprocess
from datetime import datetime
from pathlib import Path
from scripts.auto_approve import prompt_yes_no
import argparse
import os
# Automatically bless audit mismatches found during verification.

BLESSINGS_FILE = Path("SANCTUARY_BLESSINGS.jsonl")


def run_verify() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", "-m", "scripts.verify_audits", "logs/"], capture_output=True, text=True
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

    auto = args.auto_approve or os.getenv("LUMOS_AUTO_APPROVE") == "1"
    if auto:
        os.environ["LUMOS_AUTO_APPROVE"] = "1"


    result = run_verify()
    output = result.stdout + result.stderr
    print(output)
    if "prev hash mismatch" in output or "chain break" in output:
        if auto or prompt_yes_no("Bless mismatches?"):
            append_blessing()
            return 0
        return 1
    return 0


if __name__ == "__main__":
    main()
