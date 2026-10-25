from __future__ import annotations

import importlib
import os
import subprocess
from unittest.mock import Mock

import pytest

from sentientos import privilege
from scripts import launcher_gui

pytestmark = pytest.mark.no_legacy_skip


def test_import_does_not_request_privilege(monkeypatch: pytest.MonkeyPatch) -> None:
    require_admin = Mock()
    require_lumos = Mock()
    monkeypatch.setattr(privilege, "require_admin_banner", require_admin)
    monkeypatch.setattr(privilege, "require_lumos_approval", require_lumos)

    importlib.reload(launcher_gui)

    require_admin.assert_not_called()
    require_lumos.assert_not_called()


def test_main_checks_privilege_before_headless_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(privilege, "require_admin_banner", lambda: calls.append("admin"))
    monkeypatch.setattr(privilege, "require_lumos_approval", lambda: calls.append("lumos"))
    monkeypatch.setattr(launcher_gui, "tk", None)

    launcher_gui.main()

    assert calls == ["admin", "lumos"]
    assert "Tkinter not available" in capsys.readouterr().out


def test_windows_launch_uses_literal_argv_without_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    popen = Mock()
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    monkeypatch.setattr(subprocess, "Popen", popen)

    launcher_gui._launch(["--headless", "--debug", "--safe"])

    args, kwargs = popen.call_args
    assert args[0] == [
        r"C:\Windows\System32\cmd.exe",
        "/k",
        "call",
        "launch_sentientos.bat",
        "--headless",
        "--debug",
        "--safe",
    ]
    assert kwargs["shell"] is False
    assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


def test_launch_rejects_unrecognized_flag_before_process_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    popen = Mock()
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(subprocess, "Popen", popen)

    with pytest.raises(ValueError, match="unsupported launcher flag"):
        launcher_gui._launch(["--debug & whoami"])

    popen.assert_not_called()


def test_non_windows_launch_fails_closed_without_process_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    popen = Mock()
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(subprocess, "Popen", popen)

    with pytest.raises(OSError, match="only supported on Windows"):
        launcher_gui._launch(["--debug"])

    popen.assert_not_called()
