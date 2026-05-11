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


def _write_report(env: dict[str, str] | None, *, failed: int = 0, passed: int = 1) -> None:
    assert env is not None
    report_path = Path(env["SENTIENTOS_PYTEST_REPORT_PATH"])
    report_path.write_text(
        json.dumps(
            {
                "tests_collected": passed + failed,
                "tests_selected": passed + failed,
                "tests_executed": passed + failed,
                "tests_passed": passed,
                "tests_failed": failed,
                "tests_skipped": 0,
                "tests_xfailed": 0,
                "tests_xpassed": 0,
                "reporter_ok": True,
                "reporter_error": None,
            }
        ),
        encoding="utf-8",
    )


def test_targeted_missing_editable_uses_minimal_airlock_without_broad_deps(monkeypatch, tmp_path):
    pip_commands: list[list[str]] = []
    editable_statuses = iter(
        [
            EditableInstallStatus(False, "distribution-not-found"),
            EditableInstallStatus(True, "direct-url"),
        ]
    )

    def fake_run(cmd, cwd=None, env=None, capture_output=False, text=False, check=False):
        if cmd[:3] == [run_tests.sys.executable, "-m", "pip"]:
            pip_commands.append(cmd)
            return _Completed(0)
        if cmd[:3] == [run_tests.sys.executable, "-m", "pytest"]:
            _write_report(env)
            return _Completed(0)
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return _Completed(0, "abc123\n")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(run_tests, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        run_tests, "get_editable_install_status", lambda _root: next(editable_statuses)
    )
    monkeypatch.setattr(run_tests, "_imports_ok", lambda: (True, None))
    monkeypatch.setattr(run_tests.subprocess, "run", fake_run)

    code = run_tests.main(["-q", "tests/test_focused.py"])

    assert code == 0
    assert pip_commands == [
        [run_tests.sys.executable, "-m", "pip", "install", "--no-deps", "-e", "."],
        [run_tests.sys.executable, "-m", "pip", "install", *run_tests.MINIMAL_TEST_AIRLOCK_DEPS],
    ]
    assert all(f".{run_tests.INSTALL_EXTRAS}" not in part for command in pip_commands for part in command)
    payload = json.loads(
        (tmp_path / "glow" / "test_runs" / "test_run_provenance.json").read_text(encoding="utf-8")
    )
    assert payload["install_mode"] == run_tests.INSTALL_MODE_TEST_AIRLOCK_MINIMAL
    assert payload["install_attempted_modes"] == [run_tests.INSTALL_MODE_TEST_AIRLOCK_MINIMAL]
    assert payload["install_fallback_reason"] is None
    assert payload["run_intent"] == "targeted"


def test_default_full_install_failure_falls_back_to_minimal_airlock(monkeypatch, tmp_path):
    pip_commands: list[list[str]] = []
    editable_statuses = iter(
        [
            EditableInstallStatus(False, "distribution-not-found"),
            EditableInstallStatus(True, "direct-url"),
        ]
    )

    def fake_run(cmd, cwd=None, env=None, capture_output=False, text=False, check=False):
        if cmd[:3] == [run_tests.sys.executable, "-m", "pip"]:
            pip_commands.append(cmd)
            if cmd[-1] == f".{run_tests.INSTALL_EXTRAS}":
                return _Completed(1)
            return _Completed(0)
        if cmd[:3] == [run_tests.sys.executable, "-m", "pytest"]:
            _write_report(env)
            return _Completed(0)
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return _Completed(0, "def456\n")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(run_tests, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        run_tests, "get_editable_install_status", lambda _root: next(editable_statuses)
    )
    monkeypatch.setattr(run_tests, "_imports_ok", lambda: (True, None))
    monkeypatch.setattr(run_tests.subprocess, "run", fake_run)

    code = run_tests.main(["-q"])

    assert code == 0
    assert pip_commands[0] == [
        run_tests.sys.executable,
        "-m",
        "pip",
        "install",
        "-e",
        f".{run_tests.INSTALL_EXTRAS}",
    ]
    assert pip_commands[1:] == [
        [run_tests.sys.executable, "-m", "pip", "install", "--no-deps", "-e", "."],
        [run_tests.sys.executable, "-m", "pip", "install", *run_tests.MINIMAL_TEST_AIRLOCK_DEPS],
    ]
    payload = json.loads(
        (tmp_path / "glow" / "test_runs" / "test_run_provenance.json").read_text(encoding="utf-8")
    )
    assert payload["install_mode"] == run_tests.INSTALL_MODE_TEST_AIRLOCK_MINIMAL
    assert payload["install_fallback_reason"] == "full-install-failed"
    assert payload["install_attempted_modes"] == [
        run_tests.INSTALL_MODE_FULL,
        run_tests.INSTALL_MODE_TEST_AIRLOCK_MINIMAL,
    ]


def test_airlock_imports_are_checked_after_minimal_bootstrap(monkeypatch, tmp_path):
    editable_statuses = iter(
        [
            EditableInstallStatus(False, "distribution-not-found"),
            EditableInstallStatus(True, "direct-url"),
        ]
    )
    import_checks = 0

    def fake_run(cmd, cwd=None, env=None, capture_output=False, text=False, check=False):
        if cmd[:3] == [run_tests.sys.executable, "-m", "pip"]:
            return _Completed(0)
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return _Completed(0, "fedcba\n")
        raise AssertionError(f"unexpected command: {cmd}")

    def fake_imports_ok():
        nonlocal import_checks
        import_checks += 1
        return False, "fastapi import failed: missing"

    monkeypatch.setattr(run_tests, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        run_tests, "get_editable_install_status", lambda _root: next(editable_statuses)
    )
    monkeypatch.setattr(run_tests, "_imports_ok", fake_imports_ok)
    monkeypatch.setattr(run_tests.subprocess, "run", fake_run)

    code = run_tests.main(["-q", "tests/test_focused.py"])

    assert code == 1
    assert import_checks == 1
    payload = json.loads(
        (tmp_path / "glow" / "test_runs" / "test_run_provenance.json").read_text(encoding="utf-8")
    )
    assert payload["exit_reason"] == "airlock-failed"
    assert payload["install_mode"] == run_tests.INSTALL_MODE_TEST_AIRLOCK_MINIMAL


def test_actual_pytest_failures_still_fail_as_pytest_failures(monkeypatch, tmp_path):
    def fake_run(cmd, cwd=None, env=None, capture_output=False, text=False, check=False):
        if cmd[:3] == [run_tests.sys.executable, "-m", "pytest"]:
            _write_report(env, failed=1, passed=0)
            return _Completed(1)
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return _Completed(0, "badbad\n")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(run_tests, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        run_tests,
        "get_editable_install_status",
        lambda _root: EditableInstallStatus(True, "direct-url"),
    )
    monkeypatch.setattr(run_tests, "_imports_ok", lambda: (True, None))
    monkeypatch.setattr(run_tests.subprocess, "run", fake_run)

    code = run_tests.main(["-q", "tests/test_focused.py"])

    assert code == 1
    payload = json.loads(
        (tmp_path / "glow" / "test_runs" / "test_run_provenance.json").read_text(encoding="utf-8")
    )
    assert payload["exit_reason"] == "pytest-failed"
    assert payload["tests_failed"] == 1
    assert payload["metrics_status"] == "ok"


def test_bootstrap_failure_is_distinct_from_test_failure(monkeypatch, tmp_path):
    def fake_run(cmd, cwd=None, env=None, capture_output=False, text=False, check=False):
        if cmd[:3] == [run_tests.sys.executable, "-m", "pip"]:
            return _Completed(1)
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return _Completed(0, "feed01\n")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(run_tests, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        run_tests,
        "get_editable_install_status",
        lambda _root: EditableInstallStatus(False, "distribution-not-found"),
    )
    monkeypatch.setattr(run_tests.subprocess, "run", fake_run)

    code = run_tests.main(["-q", "tests/test_focused.py"])

    assert code == 1
    payload = json.loads(
        (tmp_path / "glow" / "test_runs" / "test_run_provenance.json").read_text(encoding="utf-8")
    )
    assert payload["exit_reason"] == "install-failed"
    assert payload["metrics_status"] == "unavailable"
    assert payload["tests_failed"] == 0
    assert payload["install_fallback_reason"] == "minimal-test-airlock-install-failed"


def test_naked_pytest_bypass_still_marks_run_exceptional(monkeypatch):
    monkeypatch.setenv("SENTIENTOS_ALLOW_NAKED_PYTEST", "1")

    run_intent, selection = run_tests._run_intent(
        pytest_args=["-q", "tests/test_focused.py"],
        bypass_envs=run_tests._active_bypass_envs({"SENTIENTOS_ALLOW_NAKED_PYTEST": "1"}),
    )

    assert run_intent == "exceptional"
    assert selection == ["tests/test_focused.py"]
