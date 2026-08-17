from __future__ import annotations

import json
import os
import stat
import sys
from importlib import reload
from pathlib import Path

import pytest

from api import actuator

pytestmark = pytest.mark.no_legacy_skip


def _rule(alias: str, executable: str, arguments: list[dict[str, object]]) -> dict[str, object]:
    return {"alias": alias, "executable": executable, "arguments": arguments}


def _ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rules: list[object]) -> None:
    reload(actuator)
    actuator.SANDBOX_DIR = tmp_path / "sandbox"
    actuator.SANDBOX_DIR.mkdir(exist_ok=True)
    actuator.WHITELIST = {"shell": rules, "http": [], "timeout": 5}
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: None)


def _python_rule(*arguments: dict[str, object], alias: str = "trusted") -> dict[str, object]:
    return _rule(alias, sys.executable, list(arguments))


def _literal(value: str) -> dict[str, object]:
    return {"type": "literal", "value": value}


def test_exact_executable_alias_and_complete_arguments_are_executed(tmp_path, monkeypatch):
    code = "print('trusted')"
    _ready(tmp_path, monkeypatch, [_python_rule(_literal("-c"), _literal(code), alias="diagnostic")])
    result = actuator.run_shell(["diagnostic", "-c", code])
    assert result["stdout"].strip() == "trusted"


def test_exact_configured_executable_may_be_the_lookup_key(tmp_path, monkeypatch):
    code = "print('exact-path')"
    executable = str(Path(sys.executable).resolve())
    _ready(tmp_path, monkeypatch, [_python_rule(_literal("-c"), _literal(code))])
    result = actuator.run_shell([executable, "-c", code])
    assert result["stdout"].strip() == "exact-path"


def test_one_of_is_complete_and_exact(tmp_path, monkeypatch):
    _ready(tmp_path, monkeypatch, [_python_rule(
        _literal("-c"), _literal("import sys; print(sys.argv[1:])"),
        {"type": "one_of", "values": ["brief", "full"]},
    )])
    result = actuator.run_shell(["trusted", "-c", "import sys; print(sys.argv[1:])", "brief"])
    assert "brief" in result["stdout"]


def test_legacy_cmd_is_parsing_only_and_uses_the_same_rule(tmp_path, monkeypatch):
    code = "print('legacy')"
    _ready(tmp_path, monkeypatch, [_python_rule(_literal("-c"), _literal(code), alias="diagnostic")])
    result = actuator.dispatch({"type": "shell", "cmd": f"diagnostic -c {json.dumps(code)}"})
    assert result["stdout"].strip() == "legacy"
    assert result["legacy_cmd"].startswith("diagnostic -c")


@pytest.mark.skipif(os.name != "posix", reason="process-real executable fixture requires POSIX")
def test_process_real_path_hijack_has_zero_effect(tmp_path, monkeypatch):
    marker = tmp_path / "hijacked"
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    fake = attacker / "diagnostic"
    fake.write_text(f"#!/bin/sh\ntouch {marker}\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    code = "print('trusted-path')"
    _ready(tmp_path, monkeypatch, [_python_rule(_literal("-c"), _literal(code), alias="diagnostic")])
    monkeypatch.setenv("PATH", f"{attacker}{os.pathsep}{os.environ.get('PATH', '')}")
    result = actuator.run_shell(["diagnostic", "-c", code])
    assert result["stdout"].strip() == "trusted-path"
    assert not marker.exists()


def test_denied_argument_variants_construct_zero_processes(tmp_path, monkeypatch):
    _ready(tmp_path, monkeypatch, [_python_rule(_literal("-c"), _literal("print('allowed')"))])
    calls: list[object] = []
    monkeypatch.setattr(actuator.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    variants = [
        ["trusted", "-c"],
        ["trusted", "-c", "print('allowed')", "extra"],
        ["trusted", "--version", "print('allowed')"],
        ["trusted", "-c", "print('injected')"],
        ["trusted", "script.py", "print('allowed')"],
    ]
    for argv in variants:
        with pytest.raises(PermissionError):
            actuator.run_shell(argv)
    assert calls == []


def test_one_of_denial_has_zero_effect(tmp_path, monkeypatch):
    _ready(tmp_path, monkeypatch, [_python_rule({"type": "one_of", "values": ["brief", "full"]})])
    calls: list[object] = []
    monkeypatch.setattr(actuator.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(PermissionError):
        actuator.run_shell(["trusted", "other"])
    assert calls == []


def test_legacy_bare_name_policy_is_malformed_and_zero_effect(tmp_path, monkeypatch):
    _ready(tmp_path, monkeypatch, ["python", "curl", "ping"])
    monkeypatch.setattr(actuator.subprocess, "run", lambda *a, **k: pytest.fail("process constructed"))
    with pytest.raises(PermissionError, match="structured rule required"):
        actuator.run_shell(["python", "--version"])


def test_shipped_policy_has_no_generic_process_authority():
    loaded = actuator._load_yaml(Path("config/act_whitelist.yml").read_text())
    assert loaded["shell"] == []


def test_template_expansion_is_not_authority(tmp_path, monkeypatch):
    _ready(tmp_path, monkeypatch, [])
    actuator.TEMPLATES = {"network": {"type": "shell", "argv": ["curl", "{url}"]}}
    monkeypatch.setattr(actuator.subprocess, "run", lambda *a, **k: pytest.fail("process constructed"))
    with pytest.raises(PermissionError, match="not allowed"):
        actuator.dispatch({"type": "template", "name": "network", "params": {"url": "https://example.com"}})


def test_malformed_and_non_executable_policy_paths_fail_closed(tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.write_text("not executable")
    for executable in ("python", "/definitely/missing/executable", str(plain), "bad\x00path"):
        _ready(tmp_path, monkeypatch, [_rule("tool", executable, [])])
        monkeypatch.setattr(actuator.subprocess, "run", lambda *a, **k: pytest.fail("process constructed"))
        with pytest.raises(PermissionError, match="policy is malformed"):
            actuator.run_shell(["tool"])
