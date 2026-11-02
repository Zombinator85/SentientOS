#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|\__,_|\__, |_|_|_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/
from __future__ import annotations

import os
from pathlib import Path

import pytest

import sentientos.cli.avatar_demo_cli as avatar_cli

pytestmark = pytest.mark.no_legacy_skip


def test_avatar_launcher_keeps_report_relay_opt_in_and_port_bounded():
    assert avatar_cli.parse_args([]).renderer_report_relay_port is None
    assert avatar_cli.parse_args(["--renderer-report-relay-port", "18189"]).renderer_report_relay_port == 18189
    with pytest.raises(SystemExit):
        avatar_cli.parse_args(["--renderer-report-relay-port", "0"])
    with pytest.raises(SystemExit):
        avatar_cli.parse_args(["--renderer-report-relay-port", "65536"])


def test_avatar_launcher_passes_only_the_loopback_relay_port_to_godot(monkeypatch,
                                                                       tmp_path: Path):
    binary = tmp_path / "godot"
    binary.write_text("fixture", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(avatar_cli, "resolve_godot_binary", lambda candidate: binary)
    captured: dict[str, object] = {}

    def fake_popen(command, *, env):
        captured["command"] = command
        captured["env"] = env
        return object()

    monkeypatch.setattr(avatar_cli.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("KEEP_EXISTING_VALUE", "present")
    process = avatar_cli.launch_godot(project, binary, renderer_report_relay_port=18189)
    assert process is not None
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["SENTIENTOS_RENDERER_REPORT_RELAY_PORT"] == "18189"
    assert environment["KEEP_EXISTING_VALUE"] == "present"
    assert "127.0.0.1" not in captured["command"]
