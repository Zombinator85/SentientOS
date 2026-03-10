from __future__ import annotations

import json

from scripts import run_tests


class _Completed:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


class _EditableStatus:
    def __init__(self, ok: bool = True, reason: str = "direct-url") -> None:
        self.ok = ok
        self.reason = reason


def test_bootstrap_failure_message_classifies_unavailable_metrics() -> None:
    message = run_tests._bootstrap_failure_message(
        pytest_exit_code=1,
        metrics_status="unavailable",
        reporter_error={"type": "ReporterUnavailable", "message": "pytest metrics report file was not created."},
    )
    assert message is not None
    assert message.startswith("ENVIRONMENT/BOOTSTRAP FAILURE:")


def test_bootstrap_failure_message_omits_successful_runs() -> None:
    assert run_tests._bootstrap_failure_message(0, "ok", None) is None


def test_run_tests_marks_bootstrap_metrics_failure(monkeypatch, capsys):
    provenance_path = run_tests.REPO_ROOT / "glow" / "test_runs" / "test_run_provenance.json"
    before = provenance_path.read_text(encoding="utf-8") if provenance_path.exists() else None

    def fake_run(cmd, cwd=None, env=None, capture_output=False, text=False, check=False):
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return _Completed(0, "deadbeef\n")
        if cmd[:3] == [run_tests.sys.executable, "-m", "pytest"]:
            return _Completed(1)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(run_tests, "get_editable_install_status", lambda _root: _EditableStatus())
    monkeypatch.setattr(run_tests, "_imports_ok", lambda: (True, None))
    monkeypatch.setattr(run_tests.subprocess, "run", fake_run)

    try:
        code = run_tests.main(["-q", "tests/test_placeholder.py"])
        captured = capsys.readouterr()
        assert code == 1
        assert "ENVIRONMENT/BOOTSTRAP FAILURE:" in captured.out

        payload = json.loads(provenance_path.read_text(encoding="utf-8"))
        assert payload["exit_reason"] == "bootstrap-metrics-failed"
        assert payload["metrics_status"] == "unavailable"
    finally:
        if before is None:
            if provenance_path.exists():
                provenance_path.unlink()
        else:
            provenance_path.write_text(before, encoding="utf-8")
        for snapshot in (run_tests.REPO_ROOT / "glow" / "test_runs" / "provenance").glob("*.json"):
            if "deadbeef" in snapshot.name:
                snapshot.unlink()
