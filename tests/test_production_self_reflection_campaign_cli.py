from __future__ import annotations

import os
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
