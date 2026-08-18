from __future__ import annotations

import subprocess
import sys


def test_static_reconciliation_verifier_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/verify_household_presence_talkback_reconciliation.py"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
