from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from scripts.run_workspace_change_set_lifecycle import main


def test_cli_admit_only_matches_api_stage_behavior(tmp_path: Path, capsys) -> None:
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps({"declared_target_count": 1, "targets": [{"target_id": "t", "relative_target_path": "demo.txt", "operation": "create_file", "payload_text": "hello"}]}), encoding="utf-8")
    assert main(["--proposal", str(proposal), "--workspace-root", str(tmp_path), "--mode", "admit_only", "--summary"]) == 0
    out = capsys.readouterr().out
    assert "requested_mode: admit_only" in out
    assert "stages_attempted: ['admission']" in out


def test_cli_dry_run_alias_does_not_execute(tmp_path: Path, capsys) -> None:
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps({"declared_target_count": 1, "targets": [{"target_id": "t", "relative_target_path": "demo.txt", "operation": "create_file", "payload_text": "hello"}]}), encoding="utf-8")
    assert main(["--proposal", str(proposal), "--workspace-root", str(tmp_path), "--mode", "admit_preflight_execute", "--dry-run", "--summary"]) == 0
    out = capsys.readouterr().out
    assert "requested_mode: dry_run_full_lifecycle" in out
    assert "execution_status: None" in out
    assert not (tmp_path / "demo.txt").exists()
