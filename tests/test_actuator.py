"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()


import os
import shutil
import sys
from importlib import reload
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import relay_app
from api import actuator
import pytest


def _shell_rule(alias, executable, *arguments):
    return {"alias": alias, "executable": executable,
            "arguments": [{"type": "literal", "value": value} for value in arguments]}


def _echo_rule(*arguments):
    executable = shutil.which("echo")
    assert executable is not None
    return _shell_rule("echo", executable, *arguments)

def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("RELAY_SECRET", "secret123")
    reload(actuator)
    reload(relay_app)
    return relay_app.app.test_client()


def test_run_shell_allowed(tmp_path, monkeypatch):
    reload(actuator)
    actuator.SANDBOX_DIR = tmp_path / "sb"
    actuator.SANDBOX_DIR.mkdir()
    actuator.WHITELIST = {"shell": [_echo_rule("hello")], "http": ["http://"], "timeout": 5}
    res = actuator.run_shell(["echo", "hello"])
    assert res["code"] == 0
    assert "hello" in res["stdout"]


def test_file_write(tmp_path, monkeypatch):
    reload(actuator)
    actuator.SANDBOX_DIR = tmp_path / "sandbox"
    actuator.WHITELIST = {"shell": [], "http": [], "timeout": 5}
    res = actuator.file_write("out.txt", "data")
    written = tmp_path / "sandbox" / "out.txt"
    assert written.exists()
    assert res == {"written": str(written)}


def test_run_shell_blocked():
    reload(actuator)
    actuator.WHITELIST = {"shell": [_echo_rule()], "http": ["http://"], "timeout": 5}
    import pytest
    with pytest.raises(Exception):
        actuator.run_shell(["rm", "-rf", "/"])


def test_act_logging(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload as _reload
    import memory_manager as mm
    _reload(mm)
    _reload(actuator)
    actuator.WHITELIST = {"shell": [_echo_rule("log")], "http": [], "timeout": 5}
    result = actuator.act({"type": "shell", "cmd": "echo log"})
    assert "log_id" in result
    log_path = tmp_path / "raw" / f"{result['log_id']}.json"
    assert log_path.exists()


def test_http_fetch(monkeypatch):
    reload(actuator)
    actuator.WHITELIST = {"shell": [], "http": ["http://example.com"], "timeout": 5}

    class FakeResp:
        status_code = 200
        text = "ok"

    def fake_request(method, url, **kwargs):
        fake_request.called = (method, url)
        return FakeResp()

    from types import SimpleNamespace
    monkeypatch.setattr(actuator, "optional_import", lambda *_a, **_k: SimpleNamespace(request=fake_request))
    res = actuator.http_fetch("http://example.com")
    assert res == {"status": 200, "text": "ok"}
    import pytest
    with pytest.raises(Exception):
        actuator.http_fetch("https://blocked.com")


def test_act_route_respects_whitelist(tmp_path, monkeypatch):
    client = setup(tmp_path, monkeypatch)
    actuator.WHITELIST = {"shell": [_echo_rule("hi")], "http": ["http://"], "timeout": 5}

    resp = client.post(
        "/act",
        json={"type": "shell", "cmd": "echo hi"},
        headers={"X-Relay-Secret": "secret123"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "hi" in data.get("stdout", "")
    assert "log_id" in data and "request_log_id" in data

    resp = client.post(
        "/act",
        json={"type": "shell", "cmd": "rm -rf /"},
        headers={"X-Relay-Secret": "secret123"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "error" in data


def test_sandbox_escape(tmp_path, monkeypatch):
    reload(actuator)
    actuator.SANDBOX_DIR = tmp_path / "sbox"
    actuator.SANDBOX_DIR.mkdir()
    with pytest.raises(Exception):
        actuator.file_write("../bad.txt", "oops")


def _sandbox(tmp_path):
    reload(actuator)
    actuator.SANDBOX_DIR = tmp_path / "sbox"
    actuator.SANDBOX_DIR.mkdir()
    actuator.WHITELIST = {"shell": [{
        "alias": sys.executable,
        "executable": sys.executable,
        "arguments": [
            {"type": "literal", "value": "-c"},
            {"type": "one_of", "values": ["import os; print(os.getcwd())", "pass"]},
        ],
    }], "http": [], "timeout": 5}
    return actuator.SANDBOX_DIR


def test_sandbox_normal_nested_file_write_and_nonexistent_leaf(tmp_path):
    sandbox = _sandbox(tmp_path)

    result = actuator.file_write("new/nested/out.txt", "data")

    target = sandbox / "new" / "nested" / "out.txt"
    assert target.read_text() == "data"
    assert result == {"written": str(target.resolve())}


def test_sandbox_normal_shell_cwd_descendant(tmp_path):
    sandbox = _sandbox(tmp_path)
    child = sandbox / "existing" / "child"
    child.mkdir(parents=True)

    result = actuator.run_shell(
        [sys.executable, "-c", "import os; print(os.getcwd())"], cwd="existing/child"
    )

    assert result["code"] == 0
    assert result["stdout"].strip() == str(child.resolve())


def test_sandbox_textual_sibling_prefix_exploit_is_rejected_process_real(tmp_path):
    sandbox = _sandbox(tmp_path)
    sibling = tmp_path / "sbox_evil"
    sibling.mkdir()
    escaped = sibling / "escaped.txt"
    candidate = (sandbox / "../sbox_evil/escaped.txt").resolve()
    assert str(candidate).startswith(str(sandbox.resolve()))  # proves the old flaw

    with pytest.raises(PermissionError, match="escapes sandbox"):
        actuator.file_write("../sbox_evil/escaped.txt", "escaped")

    assert not escaped.exists()


@pytest.mark.parametrize(
    "path",
    ["../outside.txt", "sub/../../outside.txt", "../sbox2/out.txt", "../sbox-old/out.txt"],
)
def test_sandbox_traversal_and_similar_siblings_are_rejected(tmp_path, path):
    _sandbox(tmp_path)
    with pytest.raises(PermissionError, match="escapes sandbox"):
        actuator.file_write(path, "escaped")


def test_sandbox_absolute_inputs_are_rejected_even_when_inside(tmp_path):
    sandbox = _sandbox(tmp_path)
    for path in (tmp_path / "outside.txt", sandbox / "inside.txt"):
        with pytest.raises(PermissionError, match="Absolute sandbox paths"):
            actuator.file_write(str(path.resolve()), "data")
        assert not path.exists()


def test_sandbox_symlink_outside_write_is_rejected(tmp_path):
    sandbox = _sandbox(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (sandbox / "link").symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(PermissionError, match="escapes sandbox"):
        actuator.file_write("link/escaped.txt", "escaped")

    assert not (outside / "escaped.txt").exists()


def test_sandbox_symlink_inside_is_allowed(tmp_path):
    sandbox = _sandbox(tmp_path)
    destination = sandbox / "destination"
    destination.mkdir()
    try:
        (sandbox / "link").symlink_to(destination, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    result = actuator.file_write("link/safe.txt", "safe")

    assert destination.joinpath("safe.txt").read_text() == "safe"
    assert result == {"written": str((destination / "safe.txt").resolve())}


@pytest.mark.parametrize("cwd", ["../outside", "../sbox_evil"])
def test_sandbox_rejected_shell_cwd_launches_zero_processes(tmp_path, monkeypatch, cwd):
    _sandbox(tmp_path)
    (tmp_path / cwd.removeprefix("../")).mkdir(exist_ok=True)
    calls = []
    monkeypatch.setattr(actuator.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    with pytest.raises(PermissionError, match="escapes sandbox"):
        actuator.run_shell([sys.executable, "-c", "pass"], cwd=cwd)

    assert calls == []


def test_sandbox_symlink_outside_cwd_launches_zero_processes(tmp_path, monkeypatch):
    sandbox = _sandbox(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (sandbox / "link").symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    calls = []
    monkeypatch.setattr(actuator.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    with pytest.raises(PermissionError, match="escapes sandbox"):
        actuator.run_shell([sys.executable, "-c", "pass"], cwd="link")

    assert calls == []


def test_sandbox_root_dot_repeated_separators_and_literal_names(tmp_path):
    sandbox = _sandbox(tmp_path)
    assert actuator._safe_path("") == sandbox.resolve()
    assert actuator._safe_path(".") == sandbox.resolve()
    assert actuator._safe_path("./child") == (sandbox / "child").resolve()
    assert actuator._safe_path("nested//child") == (sandbox / "nested" / "child").resolve()

    actuator.file_write("~/literal-$HOME.txt", "literal")
    assert (sandbox / "~" / "literal-$HOME.txt").read_text() == "literal"


@pytest.mark.parametrize("path", [None, 3, {}, [], b"bytes", "", "bad\x00name"])
def test_sandbox_malformed_file_paths_fail_closed(tmp_path, path):
    sandbox = _sandbox(tmp_path)
    with pytest.raises((ValueError, PermissionError)):
        actuator.file_write(path, "data")
    assert list(sandbox.rglob("*")) == []


def test_sandbox_ancestry_static_verifier_uses_components_not_text_prefixes():
    source = Path(actuator.__file__).read_text(encoding="utf-8")
    helper = source[source.index("def _safe_path"):source.index("\ndef file_write", source.index("def _safe_path"))]
    assert ".relative_to(sandbox_root)" in helper
    assert ".startswith(" not in helper
    assert "os.fspath" not in helper


for _sandbox_test_name in (
    "test_sandbox_normal_nested_file_write_and_nonexistent_leaf",
    "test_sandbox_normal_shell_cwd_descendant",
    "test_sandbox_textual_sibling_prefix_exploit_is_rejected_process_real",
    "test_sandbox_traversal_and_similar_siblings_are_rejected",
    "test_sandbox_absolute_inputs_are_rejected_even_when_inside",
    "test_sandbox_symlink_outside_write_is_rejected",
    "test_sandbox_symlink_inside_is_allowed",
    "test_sandbox_rejected_shell_cwd_launches_zero_processes",
    "test_sandbox_symlink_outside_cwd_launches_zero_processes",
    "test_sandbox_root_dot_repeated_separators_and_literal_names",
    "test_sandbox_malformed_file_paths_fail_closed",
    "test_sandbox_ancestry_static_verifier_uses_components_not_text_prefixes",
):
    globals()[_sandbox_test_name] = pytest.mark.no_legacy_skip(globals()[_sandbox_test_name])


def test_whitelist_pattern(monkeypatch):
    reload(actuator)
    actuator.WHITELIST = {"shell": [_echo_rule()], "http": [], "timeout": 5}
    res = actuator.run_shell(["echo"], cwd=".")
    assert res["code"] == 0
    with pytest.raises(Exception):
        actuator.run_shell(["rm"])


def test_template_expansion(monkeypatch):
    reload(actuator)
    actuator.TEMPLATES = {"greet": {"type": "shell", "argv": ["echo", "{name}"]}}
    actuator.WHITELIST = {"shell": [_echo_rule("Bob")], "http": [], "timeout": 5}
    out = actuator.dispatch({"type": "template", "name": "greet", "params": {"name": "Bob"}})
    assert "stdout" in out and "Bob" in out["stdout"]


def test_recent_logs_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload as _reload
    import memory_manager as mm
    _reload(mm)
    _reload(actuator)
    actuator.WHITELIST = {"shell": [_echo_rule("hi")], "http": [], "timeout": 5}
    actuator.act({"type": "shell", "cmd": "echo hi"})
    monkeypatch.setattr(sys, "argv", ["ac", "logs", "--last", "1"])
    actuator.main()
    out = capsys.readouterr().out
    assert "hi" in out


def test_template_prompting(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload as _reload
    import memory_manager as mm
    _reload(mm)
    _reload(actuator)
    actuator.WHITELIST = {"shell": [_echo_rule("test note")], "http": [], "timeout": 5}
    actuator.TEMPLATES = {"note": {"type": "shell", "argv": ["echo", "{text}"]}}

    monkeypatch.setattr(sys, "argv", ["ac", "template", "--name", "note"])
    monkeypatch.setattr("builtins.input", lambda prompt: "test note")
    actuator.main()
    out = capsys.readouterr().out
    assert "log_id" in out


def test_reflection_and_rate_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload as _reload
    import memory_manager as mm
    _reload(mm)
    _reload(actuator)
    actuator.WHITELIST = {"shell": [_echo_rule("hi")], "http": [], "timeout": 5}
    res1 = actuator.act({"type": "shell", "cmd": "echo hi"})
    assert "reflection" in res1
    res2 = actuator.act({"type": "shell", "cmd": "echo hi"})
    assert "error" in res2 and "Rate limit" in res2["error"]


def test_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    import importlib
    import memory_manager as mm
    importlib.reload(mm)
    importlib.reload(actuator)
    actuator.WHITELIST = {"shell": [_echo_rule("hi")], "http": [], "timeout": 5}
    out = actuator.act({"type": "shell", "cmd": "echo hi", "dry_run": True})
    assert out.get("dry_run")


def test_template_help_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    import importlib
    import memory_manager as mm
    importlib.reload(mm)
    importlib.reload(actuator)
    actuator.TEMPLATES = {"greet": {"type": "shell", "argv": ["echo", "{name}"]}}
    monkeypatch.setattr(sys, "argv", ["ac", "template_help", "--name", "greet"])
    actuator.main()
    out = capsys.readouterr().out
    assert "required" in out


def test_structured_reflection(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload as _reload
    import memory_manager as mm
    _reload(mm)
    _reload(actuator)
    actuator.WHITELIST = {"shell": [_echo_rule("hi")], "http": [], "timeout": 5}
    res = actuator.act({"type": "shell", "cmd": "echo hi"}, explanation="test", user="bob")
    assert res.get("reflection_id")
    refls = mm.recent_reflections(limit=1)
    assert refls and refls[0]["intent"]["argv"] == ["echo", "hi"]
    assert refls[0]["intent"]["legacy_cmd"] == "echo hi"
    assert refls[0]["reason"] == "test"


def test_auto_critique(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", str(tmp_path))
    from importlib import reload as _reload
    import memory_manager as mm
    _reload(mm)
    _reload(actuator)
    actuator.WHITELIST = {"shell": [_echo_rule("hi")], "http": [], "timeout": 5}
    res = actuator.act({"type": "shell", "cmd": "rm"})
    assert res["status"] == "failed" and "critique" in res
