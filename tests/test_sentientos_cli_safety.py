from __future__ import annotations

import builtins
import importlib
import sys
import types

import pytest

import sentientos.__main__ as sm


pytestmark = pytest.mark.no_legacy_skip


def _guard_no_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    real_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in ("w", "a", "+", "x")):
            raise AssertionError(f"write attempted in safe CLI command: {file}")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)


def _install_privilege_blocker(monkeypatch: pytest.MonkeyPatch) -> None:
    privilege = types.ModuleType("sentientos.privilege")

    def _blocked() -> None:
        raise RuntimeError("privilege check invoked")

    privilege.require_admin_banner = _blocked  # type: ignore[attr-defined]
    privilege.require_lumos_approval = _blocked  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentientos.privilege", privilege)


def _assert_models_not_loaded() -> None:
    assert "sentientos.local_model" not in sys.modules


def _reload_main() -> None:
    importlib.reload(sm)


def test_help_runs_without_privilege_checks(monkeypatch, capsys):
    _install_privilege_blocker(monkeypatch)
    _guard_no_writes(monkeypatch)
    sys.modules.pop("sentientos.local_model", None)
    _reload_main()

    with pytest.raises(SystemExit):
        sm.main(["--help"])

    _assert_models_not_loaded()
    out = capsys.readouterr().out
    assert "SentientOS" in out


@pytest.mark.parametrize("argv, expected", [
    (["status"], "Status:"),
    (["doctor"], "Doctor:"),
    (["--version"], "SentientOS"),
])
def test_safe_commands_skip_privilege_and_writes(monkeypatch, capsys, argv, expected):
    _install_privilege_blocker(monkeypatch)
    _guard_no_writes(monkeypatch)
    sys.modules.pop("sentientos.local_model", None)
    _reload_main()

    sm.main(argv)

    _assert_models_not_loaded()
    out = capsys.readouterr().out
    assert expected in out


def test_actionable_commands_fail_without_privilege(monkeypatch):
    _install_privilege_blocker(monkeypatch)
    _guard_no_writes(monkeypatch)
    _reload_main()
    dashboard_cli = types.ModuleType("sentientos.cli.dashboard_cli")
    avatar_cli = types.ModuleType("sentientos.cli.avatar_demo_cli")

    def _should_not_run(_argv):
        raise AssertionError("actionable CLI executed without privilege")

    dashboard_cli.main = _should_not_run  # type: ignore[attr-defined]
    avatar_cli.main = _should_not_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentientos.cli.dashboard_cli", dashboard_cli)
    monkeypatch.setitem(sys.modules, "sentientos.cli.avatar_demo_cli", avatar_cli)

    with pytest.raises(SystemExit):
        sm.main(["dashboard"])

    with pytest.raises(SystemExit):
        sm.main(["avatar-demo"])
