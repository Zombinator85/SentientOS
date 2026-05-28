from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_household_presence_camera_capture_review_decision_ledger as cli

pytestmark = pytest.mark.no_legacy_skip
FIXTURES = Path("tests/fixtures/household_presence_camera_capture_review_decision_ledger")


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, object]]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("sys.argv", ["build_household_presence_camera_capture_review_decision_ledger.py", *args])
        code = cli.main()
    out = json.loads(capsys.readouterr().out)
    return code, out


def test_build_default_validate_and_inspect_fixture(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(["build-default"], capsys)
    assert code == 0
    assert out["policy"]["schema_version"] == "household_presence_camera_capture_review_decision_ledger_policy.v1"
    code, out = run(["validate"], capsys)
    assert code == 0
    assert out["status"] == "household_presence_camera_capture_review_decision_ledger_policy_valid"
    code, out = run(["inspect-fixture", "--fixtures-dir", str(FIXTURES), "--input", "valid_deny_decision.json"], capsys)
    assert code == 0
    assert out["decision_type"] == "deny_capture_request"


def test_evaluate_validate_summarize_and_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    fixture = FIXTURES / "valid_dry_run_only_continuation.json"
    output = tmp_path / "decision.json"
    code, out = run(["evaluate", "--input", str(fixture), "--output", str(output)], capsys)
    assert code == 0
    assert out["status"] == "capture_review_decision_ledger_ready"
    assert json.loads(output.read_text(encoding="utf-8"))["ledger"]["records"][0]["safe_next_action"] == "continue_dry_run_only"
    code, out = run(["summarize", "--input", str(FIXTURES / "mixed_decision_ledger.json")], capsys)
    assert code == 0
    assert out["summary_counts"]["allow_dry_run_only_continuation"] == 1
    code, out = run(["validate", "--input", str(fixture), "--summary"], capsys)
    assert code == 0
    assert out["status"] == "capture_review_decision_ledger_ready"


def test_cli_exits_nonzero_for_blocked(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(["evaluate", "--input", str(FIXTURES / "missing_review_packet_blocked.json")], capsys)
    assert code == 1
    assert out["status"] == "capture_review_decision_ledger_blocked_missing_review_packet"
