from __future__ import annotations

import sys
from importlib import reload
from pathlib import Path

import pytest

from api import actuator
from scripts.verify_actuator_sandbox_path_retirement import verify


pytestmark = pytest.mark.no_legacy_skip


def _ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, slot: dict[str, object]) -> None:
    reload(actuator)
    actuator.SANDBOX_DIR = tmp_path / "sandbox"
    actuator.SANDBOX_DIR.mkdir(exist_ok=True)
    actuator.WHITELIST = {
        "shell": [{"alias": "trusted", "executable": sys.executable, "arguments": [slot]}],
        "http": [],
        "timeout": 5,
    }


def test_retired_sandbox_path_rule_has_zero_execution_effect(tmp_path, monkeypatch):
    _ready(tmp_path, monkeypatch, {"type": "sandbox_path"})
    effects: list[str] = []
    monkeypatch.setattr(actuator, "_snapshot_executable", lambda *args: effects.append("snapshot"))
    monkeypatch.setattr(actuator, "_open_command_cwd", lambda *args: effects.append("cwd"))
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: effects.append("authorization"))
    monkeypatch.setattr(actuator.subprocess, "run", lambda *args, **kwargs: effects.append("process"))

    with pytest.raises(PermissionError, match="policy is malformed: unsupported argument slot"):
        actuator.run_shell(["trusted", "harmless"])
    assert effects == []


def test_path_slot_alias_spellings_fail_closed(tmp_path, monkeypatch):
    for slot_type in ("sandbox-path", "sandboxPath", "path", "filesystem_path", "file_path"):
        _ready(tmp_path, monkeypatch, {"type": slot_type})
        monkeypatch.setattr(actuator, "_authorize_effect", lambda: pytest.fail("authorization occurred"))
        monkeypatch.setattr(actuator.subprocess, "run", lambda *args, **kwargs: pytest.fail("process constructed"))
        with pytest.raises(PermissionError, match="unsupported argument slot"):
            actuator.run_shell(["trusted", "harmless"])


def test_literal_path_shaped_data_remains_exact(tmp_path, monkeypatch):
    _ready(tmp_path, monkeypatch, {"type": "literal", "value": "reports/daily.txt"})
    assert actuator._authorized_shell_argv(["trusted", "reports/daily.txt"])[1] == "reports/daily.txt"


def test_retirement_static_verifier():
    verify()


def test_shipped_policy_remains_empty_and_has_no_migration_slot():
    policy = Path("config/act_whitelist.yml").read_text(encoding="utf-8")
    assert actuator._load_yaml(policy)["shell"] == []
    assert "sandbox_path" not in policy
