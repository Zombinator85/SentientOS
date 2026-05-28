from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_household_presence_camera_operator_review_trend_ledger as cli

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/household_presence_camera_operator_review_trend_ledger")


def run_cli(args: list[str], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> tuple[int, dict[str, object]]:
    monkeypatch.setattr("sys.argv", ["build_household_presence_camera_operator_review_trend_ledger.py", *args])
    code = cli.main()
    out = json.loads(capsys.readouterr().out)
    return code, out


def test_build_default_and_validate(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = run_cli(["build-default"], capsys, monkeypatch)
    assert code == 0
    assert out["policy"]["schema_version"] == "household_presence_camera_operator_review_trend_ledger_policy.v1"
    code, out = run_cli(["validate"], capsys, monkeypatch)
    assert code == 0
    assert out["status"] == "household_presence_camera_operator_review_trend_ledger_policy_valid"


def test_evaluate_summarize_and_output(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture = str(FIXTURES / "valid_repeated_capture_denials.json")
    output = tmp_path / "trend.json"
    code, out = run_cli(["evaluate", "--input", fixture, "--output", str(output)], capsys, monkeypatch)
    assert code == 0
    assert out["status"] == "operator_review_trend_ledger_ready"
    assert json.loads(output.read_text(encoding="utf-8"))["ledger"]["digest"] == out["ledger"]["digest"]
    code, summary = run_cli(["summarize", "--input", fixture], capsys, monkeypatch)
    assert code == 0
    assert summary["status"] == "operator_review_trend_ledger_ready"
    assert summary["summary_counts"]["repeated_capture_denials"] == 1


def test_inspect_fixture(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = run_cli(["inspect-fixture", "--fixtures-dir", str(FIXTURES), "--input", "valid_repeated_review_deferrals.json"], capsys, monkeypatch)
    assert code == 0
    assert "decision_records" in out


def test_cli_exits_nonzero_for_blocked(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    code, out = run_cli(["evaluate", "--input", str(FIXTURES / "missing_decision_records_blocked.json")], capsys, monkeypatch)
    assert code == 1
    assert out["status"] == "operator_review_trend_ledger_blocked_missing_decision_records"


def test_validate_policy_from_input(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"policy": {"repeated_threshold": 3}}, sort_keys=True), encoding="utf-8")
    code, out = run_cli(["validate", "--input", str(policy)], capsys, monkeypatch)
    assert code == 0
    assert out["ok"] is True
