import json
import subprocess

import pytest


@pytest.mark.parametrize("action", ["install", "start", "stop", "status"])
def test_service_command_linux_dry_run(action: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_SERVICE_DRY_RUN", "1")
    result = subprocess.run(
        ["python", "sosctl.py", "service", action],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert any(cmd[0] == "systemctl" for cmd in payload["commands"])
    assert payload.get("notices", []) is not None
    if action == "install":
        assert payload.get("yaml_available") is False
        assert {
            "dependency": "PyYAML",
            "effect": "service rendering skipped",
            "mode": "dry-run",
        } in payload.get("notices", [])


def test_service_command_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_SERVICE_DRY_RUN", "1")
    monkeypatch.setenv("SENTIENTOS_SERVICE_PLATFORM", "Windows")
    result = subprocess.run(
        ["python", "sosctl.py", "service", "start"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["system"].startswith("windows")
    assert any(cmd[0].lower().endswith("powershell.exe") for cmd in payload["commands"])
