from __future__ import annotations

import json
from pathlib import Path
import pytest

from log_utils import read_json
from sentientos.installer import AppInstaller, InstallError
from sentientos.shell import SentientShell, ShellConfig, ShellEventLogger
from sentientos.shell import cli as shell_cli


class DummyCodex:
    def __init__(self, root: Path) -> None:
        self.CODEX_SUGGEST_DIR = root / "codex"
        self.CODEX_SUGGEST_DIR.mkdir(parents=True, exist_ok=True)
        self.run_once_calls = 0
        self.confirmed: list[str] = []
        self.rejected: list[str] = []

    def run_once(self, queue) -> dict[str, object]:
        self.run_once_calls += 1
        queue.put({"event": "self_repair"})
        return {"event": "self_repair"}

    def confirm_veil_patch(self, patch_id: str) -> dict[str, object]:
        self.confirmed.append(patch_id)
        return {"patch_id": patch_id, "status": "confirmed"}

    def reject_veil_patch(self, patch_id: str) -> dict[str, object]:
        self.rejected.append(patch_id)
        return {"patch_id": patch_id, "status": "rejected"}


@pytest.fixture()
def shell_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(log_dir))
    pulses: list[dict[str, object]] = []
    logger = ShellEventLogger(
        ledger_path=log_dir / "shell_ledger.jsonl",
        pulse_publisher=lambda event: (pulses.append(event), event)[1],
    )
    codex = DummyCodex(tmp_path)
    shell = SentientShell(
        user="tester",
        logger=logger,
        config=ShellConfig(path=tmp_path / "shell_config.json"),
        request_dir=tmp_path / "requests",
        trace_dir=tmp_path / "traces",
        codex_module=codex,
        ci_runner=lambda: True,
        pulse_publisher=lambda event: event,
        home_root=tmp_path / "home" / "tester",
    )
    return {
        "shell": shell,
        "logger": logger,
        "pulses": pulses,
        "codex": codex,
        "tmp_path": tmp_path,
    }


def test_start_menu_launch_and_file_explorer(shell_environment):
    shell = shell_environment["shell"]
    logger = shell_environment["logger"]
    pulses = shell_environment["pulses"]

    assert shell.press_super_key() is True
    listing = shell.launch("File Explorer")
    assert "Documents" in listing
    assert "File Explorer" in shell.taskbar.running()

    log_entries = read_json(logger.ledger_path)
    assert any(entry["event_type"] == "app_launch" for entry in log_entries)
    assert any(event["event_type"] == "app_launch" for event in pulses)

    with pytest.raises(PermissionError):
        shell.file_explorer.open_path("/vow/secrets")


def test_installer_drag_drop_and_ci(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    events: list[dict[str, object]] = []
    logger = ShellEventLogger(
        ledger_path=tmp_path / "logs" / "shell.jsonl",
        pulse_publisher=lambda event: (events.append(event), event)[1],
    )
    installer = AppInstaller(action_logger=logger, ci_runner=lambda: True, pulse_publisher=lambda event: event)
    package = tmp_path / "google-chrome.deb"
    package.write_text("pkg", encoding="utf-8")
    result = installer.drag_and_drop(package)
    assert result["status"] == "verified"

    failing_installer = AppInstaller(
        action_logger=logger,
        ci_runner=lambda: False,
        pulse_publisher=lambda event: event,
    )
    brave = tmp_path / "brave-browser.AppImage"
    brave.write_text("pkg", encoding="utf-8")
    with pytest.raises(InstallError):
        failing_installer.install_via_button(brave)


def test_dashboard_veil_request_flow(shell_environment, tmp_path: Path):
    shell = shell_environment["shell"]
    codex = shell_environment["codex"]

    veil_metadata = {
        "patch_id": "veil-123",
        "status": "pending",
        "files_changed": ["sentientos/shell/__init__.py"],
    }
    (codex.CODEX_SUGGEST_DIR / "veil-123.veil.json").write_text(
        json.dumps(veil_metadata, indent=2),
        encoding="utf-8",
    )

    snapshot = shell.dashboard.refresh()
    assert snapshot["veil_requests"][0]["patch_id"] == "veil-123"

    shell.dashboard.confirm_veil_request("veil-123")
    assert "veil-123" in codex.confirmed

    (codex.CODEX_SUGGEST_DIR / "veil-456.veil.json").write_text(
        json.dumps({"patch_id": "veil-456", "status": "pending"}),
        encoding="utf-8",
    )
    shell.dashboard.reject_veil_request("veil-456")
    assert "veil-456" in codex.rejected


def test_codex_console_prompt_and_trace(shell_environment):
    shell = shell_environment["shell"]
    tmp_path: Path = shell_environment["tmp_path"]
    request_path = shell.run_codex_expansion("Investigate sequence", context="tests")
    assert request_path.exists()

    trace_dir = tmp_path / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_file = trace_dir / "trace_20240101.json"
    trace_file.write_text(json.dumps({"ts": "2024-01-01T00:00:00", "summary": "ok"}), encoding="utf-8")

    traces = shell.codex_console.load_reasoning_traces(limit=1)
    assert traces[0]["summary"] == "ok"

    result = shell.codex_console.trigger_self_repair()
    assert result == {"event": "self_repair"}


def test_cli_harness_start_menu_and_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys):
    class StubStartMenu:
        def __init__(self) -> None:
            self.apps = ["File Explorer", "Lumos Dashboard"]

        def list_applications(self):
            return list(self.apps)

        def list_pinned(self):
            return self.apps[:1]

        def search(self, query: str):
            return {"apps": [app for app in self.apps if query.lower() in app.lower()], "settings": []}

    class StubShell:
        def __init__(self) -> None:
            self.start_menu = StubStartMenu()

        def launch(self, name: str):
            return {"launched": name}

        def search(self, query: str):
            return self.start_menu.search(query)

        def install_via_double_click(self, path: Path):
            return {"status": "verified", "package_path": str(path)}

        def install_from_button(self, path: Path):
            return {"status": "verified", "package_path": str(path)}

        def install_via_drag_and_drop(self, path: Path):
            return {"status": "verified", "package_path": str(path)}

    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(shell_cli, "_build_shell", lambda: StubShell())

    assert shell_cli.main(["start-menu", "--list"]) == 0
    assert "File Explorer" in capsys.readouterr().out

    assert shell_cli.main(["start-menu", "--search", "Lumos"]) == 0
    assert "Lumos Dashboard" in capsys.readouterr().out

    package = tmp_path / "demo.deb"
    package.write_text("pkg", encoding="utf-8")
    assert shell_cli.main(["install", str(package), "--method", "drag"]) == 0
    install_output = capsys.readouterr().out
    assert "verified" in install_output
