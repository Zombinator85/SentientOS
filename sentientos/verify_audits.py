from __future__ import annotations

"""Portable verify_audits module entrypoint."""

import subprocess
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_AUDITS_SCRIPT = REPO_ROOT / "scripts" / "verify_audits.py"


def main(argv: Sequence[str] | None = None) -> int:
    forwarded = list(argv) if argv is not None else sys.argv[1:]
    command = [sys.executable, str(VERIFY_AUDITS_SCRIPT), *forwarded]
    completed = subprocess.run(command, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
