from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_household_presence_camera_dry_run_continuation_gate as cli

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/household_presence_camera_dry_run_continuation_gate")


def run_cli(args: list[str], capsys, monkeypatch) -> tuple[int, dict[str, object]]:
    monkeypatch.setattr("sys.argv", ["build_household_presence_camera_dry_run_continuation_gate.py", *args])
    code = cli.main()
    out = json.loads(capsys.readouterr().out)
    return code, out


def test_build_default_and_validate(capsys, monkeypatch) -> None:
    code, out = run_cli(["build-default"], capsys, monkeypatch)
    assert code == 0
    assert out["policy"]["schema_version"] == "household_presence_camera_dry_run_continuation_gate_policy.v1"
    code, out = run_cli(["validate"], capsys, monkeypatch)
    assert code == 0
    assert out["status"] == "household_presence_camera_dry_run_continuation_gate_policy_valid"


def test_evaluate_summarize_and_output(capsys, monkeypatch, tmp_path) -> None:
    output = tmp_path / "gate.json"
    input_path = FIXTURES / "valid_continue_dry_run_only_review.json"
    code, out = run_cli(["evaluate", "--input", str(input_path), "--output", str(output)], capsys, monkeypatch)
    assert code == 0
    assert out["status"] == "dry_run_continuation_gate_ready"
    assert output.exists()
    code, summary = run_cli(["summarize", "--input", str(input_path), "--summary"], capsys, monkeypatch)
    assert code == 0
    assert summary["status"] == "dry_run_continuation_gate_ready"
    assert summary["digest"]


def test_validate_input_policy_and_inspect_fixture(capsys, monkeypatch) -> None:
    code, out = run_cli(["validate", "--input", str(FIXTURES / "mixed_scope_diagnostic_warning.json")], capsys, monkeypatch)
    assert code == 0
    assert out["status"] == "dry_run_continuation_gate_ready_with_warnings"
    code, inspected = run_cli(["inspect-fixture", "--fixture-name", "valid_continue_dry_run_only_review.json"], capsys, monkeypatch)
    assert code == 0
    assert inspected["review_packet_digest"] == "review-digest-001"


def test_blocked_cli_exits_nonzero(capsys, monkeypatch) -> None:
    code, out = run_cli(["evaluate", "--input", str(FIXTURES / "missing_review_packet_blocked.json")], capsys, monkeypatch)
    assert code == 1
    assert out["status"] == "dry_run_continuation_gate_blocked_missing_review_packet"
