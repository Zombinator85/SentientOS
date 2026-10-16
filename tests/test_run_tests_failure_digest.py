from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_tests
from scripts.editable_install import EditableInstallStatus

pytestmark = pytest.mark.no_legacy_skip


class _Completed:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


def test_successful_run_removes_prior_failure_digest(monkeypatch, tmp_path):
    run_dir = tmp_path / "glow" / "test_runs"
    run_dir.mkdir(parents=True)
    stale_digest = run_dir / "test_failure_digest.json"
    stale_digest.write_text('{"failure_groups":[{"nodeid":"old failure"}]}', encoding="utf-8")

    def fake_run(cmd, cwd=None, env=None, capture_output=False, text=False, check=False):
        if cmd[:3] == [run_tests.sys.executable, "-m", "pytest"]:
            assert env is not None
            report_path = Path(env["SENTIENTOS_PYTEST_REPORT_PATH"])
            report_path.write_text(
                json.dumps(
                    {
                        "tests_collected": 1,
                        "tests_selected": 1,
                        "tests_executed": 1,
                        "tests_passed": 1,
                        "tests_failed": 0,
                        "tests_skipped": 0,
                        "tests_xfailed": 0,
                        "tests_xpassed": 0,
                        "reporter_ok": True,
                        "reporter_error": None,
                        "selected_node_ids": ["tests/test_focused.py::test_ok"],
                        "node_outcomes": [
                            {
                                "node_id": "tests/test_focused.py::test_ok",
                                "phase": "call",
                                "outcome": "passed",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            return _Completed(0)
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return _Completed(0, "goodsha\n")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(run_tests, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        run_tests,
        "get_editable_install_status",
        lambda _root: EditableInstallStatus(True, "direct-url"),
    )
    monkeypatch.setattr(run_tests, "_imports_ok", lambda: (True, None))
    monkeypatch.setattr(run_tests.subprocess, "run", fake_run)

    assert run_tests.main(["-q", "tests/test_focused.py"]) == 0
    assert not stale_digest.exists()
