from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.no_legacy_skip
def test_runner_cli_lists_preregister_run_and_score_commands():
    result = subprocess.run([sys.executable, "scripts/run_codex_subject_epistemic_pilot.py", "--help"],
        capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "preregister" in result.stdout
    assert "run" in result.stdout
    assert "score" in result.stdout
