from __future__ import annotations

import json
import os
import stat
import sys
from importlib import reload
from pathlib import Path

import pytest

from api import actuator
from scripts.verify_actuator_command_environment_custody import verify

pytestmark = pytest.mark.no_legacy_skip


def _literal(value: str) -> dict[str, object]:
    return {"type": "literal", "value": value}


def _ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *arguments: str) -> None:
    reload(actuator)
    actuator.SANDBOX_DIR = tmp_path / "sandbox"
    actuator.SANDBOX_DIR.mkdir()
    actuator.WHITELIST = {
        "shell": [{
            "alias": "python",
            "executable": sys.executable,
            "arguments": [_literal(value) for value in arguments],
        }],
        "http": [],
        "timeout": 1,
    }
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: None)


def test_exact_command_gets_empty_environment_and_reports_output(tmp_path, monkeypatch):
    keys = ["SENTIENTOS_PARENT_SECRET", "PATH", "PYTHONPATH", "HOME", "HTTPS_PROXY", "LD_PRELOAD"]
    code = "import json,os,sys;print(json.dumps({k:os.environ.get(k) for k in sys.argv[1:]}));print('stderr',file=sys.stderr);sys.exit(7)"
    _ready(tmp_path, monkeypatch, "-c", code, *keys)
    for key in keys:
        monkeypatch.setenv(key, "should-not-cross-boundary")

    result = actuator.run_shell(["python", "-c", code, *keys])

    assert json.loads(result["stdout"])["SENTIENTOS_PARENT_SECRET"] is None
    assert all(value is None for value in json.loads(result["stdout"]).values())
    assert result == {"code": 7, "stdout": result["stdout"], "stderr": "stderr\n"}


def test_parent_pythonpath_cannot_execute_attacker_module(tmp_path, monkeypatch):
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    marker = tmp_path / "marker"
    (attacker / "ambient_attack.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
    code = "import importlib.util;print(importlib.util.find_spec('ambient_attack') is None)"
    _ready(tmp_path, monkeypatch, "-c", code)
    monkeypatch.setenv("PYTHONPATH", str(attacker))

    result = actuator.run_shell(["python", "-c", code])

    assert result["code"] == 0
    assert result["stdout"].strip() == "True"
    assert not marker.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX inheritable descriptor witness")
def test_inheritable_parent_descriptor_is_closed(tmp_path, monkeypatch):
    read_fd, write_fd = os.pipe()
    try:
        os.set_inheritable(read_fd, True)
        code = "import os,sys\ntry: os.fstat(int(sys.argv[1])); print('open')\nexcept OSError: print('closed')"
        _ready(tmp_path, monkeypatch, "-c", code, str(read_fd))
        result = actuator.run_shell(["python", "-c", code, str(read_fd)])
        assert result["stdout"].strip() == "closed"
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_child_stdin_is_deterministic_eof(tmp_path, monkeypatch):
    code = "import sys;print(sys.stdin.buffer.read() == b'')"
    _ready(tmp_path, monkeypatch, "-c", code)
    assert actuator.run_shell(["python", "-c", code])["stdout"].strip() == "True"


@pytest.mark.skipif(os.name != "posix", reason="portable executable helper fixture requires POSIX")
def test_parent_path_cannot_select_attacker_helper(tmp_path, monkeypatch):
    attacker = tmp_path / "bin"
    attacker.mkdir()
    marker = tmp_path / "helper-marker"
    helper = attacker / "ambient-helper"
    helper.write_text(f"#!/bin/sh\necho selected > {marker}\n")
    helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
    code = "import subprocess; p=subprocess.run(['ambient-helper'],capture_output=True); print(p.returncode)"
    _ready(tmp_path, monkeypatch, "-c", code)
    monkeypatch.setenv("PATH", str(attacker))
    result = actuator.run_shell(["python", "-c", code])
    assert result["code"] != 0  # the child cannot locate the bare helper
    assert not marker.exists()


@pytest.mark.parametrize("field", [
    "env", "environment", "stdin", "pass_fds", "close_fds", "shell",
    "executable", "creationflags", "startupinfo",
])
def test_unknown_process_control_fields_are_rejected_before_effect(tmp_path, monkeypatch, field):
    code = "print('never')"
    _ready(tmp_path, monkeypatch, "-c", code)
    effects: list[bool] = []
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: effects.append(True))
    monkeypatch.setattr(actuator.subprocess, "run", lambda *a, **k: pytest.fail("process constructed"))
    with pytest.raises(ValueError, match="unsupported shell intent fields"):
        actuator.dispatch({"type": "shell", "argv": ["python", "-c", code], field: "hostile"})
    assert effects == []


def test_legacy_template_and_normalized_async_intents_share_custody(tmp_path, monkeypatch):
    code = "print('PATH' not in __import__('os').environ)"
    _ready(tmp_path, monkeypatch, "-c", code)
    legacy = actuator.dispatch({"type": "shell", "cmd": f"python -c {json.dumps(code)}"})
    actuator.TEMPLATES = {"check": {"type": "shell", "argv": ["python", "-c", code]}}
    template = actuator.dispatch({"type": "template", "name": "check", "params": {}})
    queued = actuator.dispatch(actuator._normalize_intent({"type": "shell", "cmd": f"python -c {json.dumps(code)}"}))
    assert [legacy["stdout"].strip(), template["stdout"].strip(), queued["stdout"].strip()] == ["True"] * 3


def test_timeout_remains_bounded(tmp_path, monkeypatch):
    code = "import time;time.sleep(2)"
    _ready(tmp_path, monkeypatch, "-c", code)
    actuator.WHITELIST["timeout"] = 0.01
    with pytest.raises(RuntimeError, match="execution timeout"):
        actuator.run_shell(["python", "-c", code])


def test_static_environment_custody_verifier():
    verify(Path(actuator.__file__))
