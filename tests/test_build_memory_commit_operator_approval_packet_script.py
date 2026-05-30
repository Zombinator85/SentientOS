from __future__ import annotations

import json
import pytest
from pathlib import Path

from scripts import build_memory_commit_operator_approval_packet as script

pytestmark = pytest.mark.no_legacy_skip

FIXTURES = Path("tests/fixtures/memory_commit_operator_approval_packet")


def test_cli_build_default_validate_summarize_evaluate_and_inspect(tmp_path, capsys) -> None:
    assert script.main.__name__ == "main"
    import sys
    old = sys.argv
    try:
        sys.argv = ["build_memory_commit_operator_approval_packet.py", "build-default"]
        assert script.main() == 0
        assert "default_approval_posture" in capsys.readouterr().out
        sys.argv = ["build_memory_commit_operator_approval_packet.py", "validate"]
        assert script.main() == 0
        assert '"status": "valid"' in capsys.readouterr().out
        fixture = FIXTURES / "valid_ai_capsule_commit_approval_candidate.json"
        out = tmp_path / "approval.json"
        sys.argv = ["build_memory_commit_operator_approval_packet.py", "evaluate", "--input", str(fixture), "--output", str(out)]
        assert script.main() == 0
        assert json.loads(out.read_text(encoding="utf-8"))["status"] == "memory_commit_operator_approval_ready"
        sys.argv = ["build_memory_commit_operator_approval_packet.py", "summarize", "--input", str(fixture)]
        assert script.main() == 0
        assert "summary_counts" in capsys.readouterr().out
        sys.argv = ["build_memory_commit_operator_approval_packet.py", "inspect-fixture", "--fixtures-dir", str(FIXTURES), "--fixture-name", "valid_noop_commit_approval_candidate.json"]
        assert script.main() == 0
        assert "noop_commit_approval_candidate" in capsys.readouterr().out
    finally:
        sys.argv = old


def test_cli_exits_nonzero_for_blocked_fixture(capsys) -> None:
    import sys
    old = sys.argv
    try:
        sys.argv = ["build_memory_commit_operator_approval_packet.py", "evaluate", "--input", str(FIXTURES / "live_write_claim_blocked.json")]
        assert script.main() == 1
        assert "memory_commit_operator_approval_blocked_live_write_claim" in capsys.readouterr().out
    finally:
        sys.argv = old
