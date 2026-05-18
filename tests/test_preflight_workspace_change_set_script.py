from __future__ import annotations

import json

import pytest

from scripts import preflight_workspace_change_set as cli

pytestmark = pytest.mark.no_legacy_skip


def test_cli_requires_workspace_root_and_target(capsys):
    assert cli.main([]) == 2
    assert cli.main(["--workspace-root", "/tmp/example"]) == 2


def test_cli_supports_multiple_targets_summary_without_target_writes(tmp_path, capsys):
    result = cli.main(["--workspace-root", str(tmp_path), "--target", "demo.txt=hello", "--target", "docs-demo.txt=docs", "--summary"])
    out = capsys.readouterr().out
    assert result == 0
    assert "preflight/planning only: true" in out
    assert "target writes performed: false" in out
    assert not (tmp_path / "demo.txt").exists()
    assert not (tmp_path / "docs-demo.txt").exists()


def test_cli_output_writes_explicit_artifact_only(tmp_path, capsys):
    output = tmp_path / "change_set_preflight.json"
    result = cli.main(["--workspace-root", str(tmp_path), "--target", "demo.txt=hello", "--output", str(output), "--summary"])
    assert result == 0
    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["preflight_planning_only"] is True
    assert data["target_write_performed"] is False
    assert not (tmp_path / "demo.txt").exists()


@pytest.mark.parametrize("target", ["/abs.txt=hello", "../escape.txt=hello", "wild*.txt=hello"])
def test_cli_rejects_unsafe_target_paths(tmp_path, target):
    assert cli.main(["--workspace-root", str(tmp_path), "--target", target, "--summary"]) == 2


def test_cli_update_existing_reads_digest_but_does_not_write(tmp_path, capsys):
    existing = tmp_path / "existing.txt"
    existing.write_text("existing\n", encoding="utf-8")
    result = cli.main(["--workspace-root", str(tmp_path), "--operation", "update_file", "--target", "existing.txt=updated", "--summary"])
    assert result == 0
    assert existing.read_text(encoding="utf-8") == "existing\n"
    assert "runner/orchestrator invoked: false" in capsys.readouterr().out


def test_cli_refuses_unsafe_output_path(tmp_path):
    assert cli.main(["--workspace-root", str(tmp_path), "--target", "demo.txt=hello", "--output", str(tmp_path / "missing" / "artifact.json")]) == 2
