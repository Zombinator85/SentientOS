from __future__ import annotations

import json
from pathlib import Path

from scripts import run_tests


class _Completed:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


def test_proof_mode_fails_cleanly_when_reporter_payload_missing(monkeypatch, capsys):
    original = run_tests.REPO_ROOT / "glow" / "test_runs" / "test_run_provenance.json"
    before = original.read_text(encoding="utf-8") if original.exists() else None

    def fake_run(cmd, cwd=None, env=None, capture_output=False, text=False, check=False):
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return _Completed(0, "deadbeef\n")
        if cmd[:3] == [run_tests.sys.executable, "-m", "pytest"]:
            return _Completed(0)
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(run_tests.subprocess, "run", fake_run)
    monkeypatch.setattr(run_tests, "_imports_ok", lambda: (True, None))

    monkeypatch.setenv("SENTIENTOS_CI_REQUIRE_DEFAULT_INTENT", "1")

    try:
        code = run_tests.main(["-q"])
        captured = capsys.readouterr()
        assert code == 1
        assert "Metrics reporter failed; cannot certify proof mode." in captured.out

        payload = json.loads(original.read_text(encoding="utf-8"))
        assert payload["metrics_status"] == "unavailable"
        assert payload["reporter_ok"] is False
        assert payload["reporter_error"]["type"] == "ReporterUnavailable"
    finally:
        if before is None:
            if original.exists():
                original.unlink()
        else:
            original.write_text(before, encoding="utf-8")
        for snapshot in (run_tests.REPO_ROOT / "glow" / "test_runs" / "provenance").glob("*.json"):
            if "deadbeef" in snapshot.name:
                snapshot.unlink()
