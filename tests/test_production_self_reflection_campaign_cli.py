#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/
from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

import os
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


def test_cli_run_one_rejects_unverified_json_before_campaign_access(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    campaign_root = tmp_path / "campaign"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_production_self_reflection_campaign.py",
            "run-one",
            "--campaign-root",
            str(campaign_root),
            "--observed",
            str(tmp_path / "untrusted-observations.json"),
            "--evidence-bundle",
            str(tmp_path / "untrusted-evidence.json"),
        ],
        cwd=repository,
        env={**os.environ, "PYTHONPATH": str(repository)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "run-one requires an in-process live transition owner" in result.stderr
    assert not campaign_root.exists()


def test_read_only_report_verifier_does_not_create_a_missing_campaign(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    campaign_root = tmp_path / "missing-campaign"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_campaign_report.py",
            "--campaign-root",
            str(campaign_root),
        ],
        cwd=repository,
        env={**os.environ, "PYTHONPATH": str(repository)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert json.loads(result.stdout) == {
        "campaign_advanced": False,
        "effect_performed": False,
        "execution_allowed": False,
        "grants_authority": False,
        "reason": "campaign_protocol_unavailable",
        "read_only": True,
        "status": "campaign_report_verification_failed",
    }
    assert not campaign_root.exists()
