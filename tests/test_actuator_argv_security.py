from __future__ import annotations

import sys
from importlib import reload

import pytest

from api import actuator

pytestmark = pytest.mark.no_legacy_skip

def _rule(executable, *arguments, alias=None):
    return {"alias": alias or executable, "executable": executable,
            "arguments": [{"type": "literal", "value": value} for value in arguments]}


def _shell_ready(tmp_path, monkeypatch, executable=sys.executable, arguments=(), alias=None):
    reload(actuator)
    actuator.SANDBOX_DIR = tmp_path / "shell-sandbox"
    actuator.SANDBOX_DIR.mkdir()
    actuator.WHITELIST = {"shell": [_rule(executable, *arguments, alias=alias)], "http": [], "timeout": 5}
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: None)


def test_explicit_argv_is_exact_and_shell_false(tmp_path, monkeypatch):
    _shell_ready(tmp_path, monkeypatch, sys.executable, ("hello;world", "$HOME", "*.txt"), "echo")
    seen = {}

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(argv, **kwargs):
        seen.update(argv=argv, kwargs=kwargs)
        return Result()

    monkeypatch.setattr(actuator.subprocess, "run", fake_run)
    result = actuator.run_shell(["echo", "hello;world", "$HOME", "*.txt"])
    assert result["code"] == 0
    assert seen["argv"] == (str(__import__("pathlib").Path(sys.executable).resolve()), "hello;world", "$HOME", "*.txt")
    assert seen["kwargs"]["shell"] is False


def test_process_real_metacharacters_are_inert(tmp_path, monkeypatch):
    values = [";", "|", "&&", ">", "$HOME", "*.txt"]
    code = "import json,sys; print(json.dumps(sys.argv[1:]))"
    _shell_ready(tmp_path, monkeypatch, sys.executable, ("-c", code, *values))
    result = actuator.run_shell([sys.executable, "-c", code, *values])
    import json
    assert json.loads(result["stdout"]) == values


def test_legacy_shell_grammar_is_rejected(tmp_path, monkeypatch):
    _shell_ready(tmp_path, monkeypatch, sys.executable, (), "echo")
    commands = [
        "echo ok; echo no", "echo ok && echo no", "echo ok || echo no",
        "echo ok | cat", "echo ok > out", "echo < in", "echo $(id)",
        "echo `id`", "echo ok\necho no", "echo <(cat)", "echo ok &",
    ]
    for cmd in commands:
        with pytest.raises(ValueError, match="rejected shell grammar"):
            actuator.dispatch({"type": "shell", "cmd": cmd})


def test_malformed_or_over_budget_argv_fails_closed(tmp_path, monkeypatch):
    _shell_ready(tmp_path, monkeypatch, sys.executable, (), "echo")
    called = False
    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
    monkeypatch.setattr(actuator.subprocess, "run", forbidden)
    cases = [
        ([], "missing command"),
        (["echo", 3], "invalid argument"),
        (["echo", "bad\x00arg"], "invalid argument"),
        (["echo"] + ["x"] * actuator.MAX_ARGV_COUNT, "argument budget exceeded"),
        (["echo", "x" * (actuator.MAX_ARGUMENT_BYTES + 1)], "argument budget exceeded"),
    ]
    for argv, message in cases:
        with pytest.raises(ValueError, match=message):
            actuator.dispatch({"type": "shell", "argv": argv})
    assert not called


def test_executable_whitelist_is_exact_not_prefix(tmp_path, monkeypatch):
    _shell_ready(tmp_path, monkeypatch, sys.executable, ("arg",), "python")
    monkeypatch.setattr(actuator.subprocess, "run", lambda *a, **k: pytest.fail("process launched"))
    with pytest.raises(PermissionError, match="shell command not allowed"):
        actuator.run_shell(["python-evil", "arg"])


def test_template_metacharacters_remain_one_argument(tmp_path, monkeypatch):
    _shell_ready(tmp_path, monkeypatch, sys.executable, ("hello; touch nope",), "echo")
    actuator.TEMPLATES = {"greet": {"type": "shell", "argv": ["echo", "{name}"]}}
    seen = {}
    class Result:
        returncode = 0
        stdout = ""
        stderr = ""
    monkeypatch.setattr(actuator.subprocess, "run", lambda argv, **kwargs: (seen.setdefault("argv", argv), Result())[1])
    actuator.dispatch({"type": "template", "name": "greet", "params": {"name": "hello; touch nope"}})
    assert seen["argv"] == (str(__import__("pathlib").Path(sys.executable).resolve()), "hello; touch nope")
    assert actuator.template_placeholders("greet") == {"name"}


def test_dry_run_reports_structured_argv_and_launches_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    import memory_manager as mm
    reload(mm)
    reload(actuator)
    actuator.LAST_EXECUTION.clear()
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: None)
    monkeypatch.setattr(actuator.subprocess, "run", lambda *a, **k: pytest.fail("process launched"))
    result = actuator.act({"type": "shell", "cmd": "echo 'hello world'", "dry_run": True})
    assert result["dry_run"] is True
    assert result["intent"]["argv"] == ["echo", "hello world"]
    assert result["intent"]["legacy_cmd"] == "echo 'hello world'"


def test_async_queues_copied_structured_argv(tmp_path, monkeypatch):
    _shell_ready(tmp_path, monkeypatch, sys.executable, ("safe",), "echo")
    monkeypatch.setattr(actuator.threading.Thread, "start", lambda self: None)
    actuator._worker_started = False
    submitted = {"type": "shell", "argv": ["echo", "safe"]}
    action_id = actuator.start_async(submitted)
    submitted["argv"][1] = "changed"
    queued_id, queued, _, _ = actuator.TASK_QUEUE.get_nowait()
    actuator.TASK_QUEUE.task_done()
    assert queued_id == action_id
    assert queued["argv"] == ["echo", "safe"]


def test_logging_and_reflection_record_structured_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    import memory_manager as mm
    reload(mm)
    reload(actuator)
    actuator.LAST_EXECUTION.clear()
    actuator.SANDBOX_DIR = tmp_path / "sb-log"
    actuator.SANDBOX_DIR.mkdir()
    actuator.WHITELIST = {"shell": [_rule(sys.executable, "logged", alias="echo")], "http": [], "timeout": 5}
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: None)
    result = actuator.act({"type": "shell", "cmd": "echo logged"})
    reflection = mm.recent_reflections(limit=1)[0]
    assert reflection["intent"]["argv"] == ["echo", "logged"]
    assert reflection["intent"]["legacy_cmd"] == "echo logged"
    assert result["argv"] == ["echo", "logged"]


def test_cwd_restriction_and_authorization_remain_at_effect(tmp_path, monkeypatch):
    _shell_ready(tmp_path, monkeypatch, sys.executable, ("safe",), "echo")
    calls = []
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: calls.append("authorized"))
    monkeypatch.setattr(actuator.subprocess, "run", lambda *a, **k: pytest.fail("process launched"))
    with pytest.raises(PermissionError, match="escapes sandbox"):
        actuator.run_shell(["echo", "safe"], cwd="../outside")
    # Inspection-only cwd admission fails before the protected privilege boundary.
    assert calls == []


def test_blocked_executable_never_executes(tmp_path, monkeypatch):
    _shell_ready(tmp_path, monkeypatch, sys.executable, (), "echo")
    monkeypatch.setattr(actuator.subprocess, "run", lambda *a, **k: pytest.fail("process launched"))
    with pytest.raises(PermissionError, match="shell command not allowed"):
        actuator.run_shell(["rm", "-rf", "/"])


def test_rate_limit_remains_intact(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    import memory_manager as mm
    reload(mm)
    reload(actuator)
    actuator.LAST_EXECUTION.clear()
    actuator.SANDBOX_DIR = tmp_path / "rate-sandbox"
    actuator.SANDBOX_DIR.mkdir()
    actuator.WHITELIST = {"shell": [_rule(sys.executable, "one", alias="echo")], "http": [], "timeout": 5}
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: None)
    assert actuator.act({"type": "shell", "argv": ["echo", "one"]})["status"] == "finished"
    assert "Rate limit" in actuator.act({"type": "shell", "argv": ["echo", "two"]})["error"]


def test_static_process_surface_verifier():
    from scripts.verify_actuator_process_execution import verify
    assert verify() == []
