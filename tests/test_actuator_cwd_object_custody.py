from __future__ import annotations

import os
import sys
from importlib import reload
from pathlib import Path

import pytest

from api import actuator
from scripts.verify_actuator_cwd_object_custody import verify

pytestmark = [pytest.mark.no_legacy_skip, pytest.mark.skipif(sys.platform != "linux", reason="Linux /proc fd cwd custody")]


def _literal(value: str) -> dict[str, object]:
    return {"type": "literal", "value": value}


def _ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str) -> Path:
    reload(actuator)
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    actuator.SANDBOX_DIR = sandbox
    actuator.WHITELIST = {"shell": [{
        "alias": "python", "executable": sys.executable,
        "arguments": [_literal("-c"), _literal(code)],
    }], "http": [], "timeout": 5}
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: None)
    return sandbox


def _write_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    code = "from pathlib import Path;Path('marker').write_text('bound')"
    return _ready(tmp_path, monkeypatch, code), code


def test_dot_cwd_process_real_success(tmp_path, monkeypatch):
    sandbox, code = _write_marker(tmp_path, monkeypatch)
    result = actuator.run_shell(["python", "-c", code], cwd=".")
    assert result == {"code": 0, "stdout": "", "stderr": ""}
    assert (sandbox / "marker").read_text() == "bound"


def test_nested_existing_cwd_process_real_success(tmp_path, monkeypatch):
    sandbox, code = _write_marker(tmp_path, monkeypatch)
    nested = sandbox / "existing" / "child"
    nested.mkdir(parents=True)
    assert actuator.run_shell(["python", "-c", code], cwd="existing//./child")["code"] == 0
    assert (nested / "marker").read_text() == "bound"


def test_authorization_time_symlink_replacement_cannot_redirect_cwd(tmp_path, monkeypatch):
    sandbox, code = _write_marker(tmp_path, monkeypatch)
    work = sandbox / "work"
    work.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    def replace() -> None:
        work.rename(sandbox / "original")
        work.symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(actuator, "_authorize_effect", replace)
    assert actuator.run_shell(["python", "-c", code], cwd="work")["code"] == 0
    assert (sandbox / "original" / "marker").read_text() == "bound"
    assert not (outside / "marker").exists()


def test_authorization_time_directory_replacement_cannot_redirect_cwd(tmp_path, monkeypatch):
    sandbox, code = _write_marker(tmp_path, monkeypatch)
    work = sandbox / "work"
    work.mkdir()

    def replace() -> None:
        work.rename(sandbox / "original")
        work.mkdir()

    monkeypatch.setattr(actuator, "_authorize_effect", replace)
    assert actuator.run_shell(["python", "-c", code], cwd="work")["code"] == 0
    assert (sandbox / "original" / "marker").read_text() == "bound"
    assert not (work / "marker").exists()


def test_authorization_time_sandbox_root_replacement_cannot_redirect_cwd(tmp_path, monkeypatch):
    sandbox, code = _write_marker(tmp_path, monkeypatch)
    (sandbox / "work").mkdir()
    original_root = tmp_path / "original-root"

    def replace() -> None:
        sandbox.rename(original_root)
        sandbox.mkdir()
        (sandbox / "work").mkdir()

    monkeypatch.setattr(actuator, "_authorize_effect", replace)
    assert actuator.run_shell(["python", "-c", code], cwd="work")["code"] == 0
    assert (original_root / "work" / "marker").read_text() == "bound"
    assert not (sandbox / "work" / "marker").exists()


@pytest.mark.parametrize("inward", [True, False], ids=["inward", "outward"])
def test_cwd_symlinks_are_denied_before_authorization_and_process(tmp_path, monkeypatch, inward):
    sandbox, code = _write_marker(tmp_path, monkeypatch)
    target = sandbox / "target" if inward else tmp_path / "outside"
    target.mkdir()
    (sandbox / "link").symlink_to(target, target_is_directory=True)
    effects: list[bool] = []
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: effects.append(True))
    monkeypatch.setattr(actuator.subprocess, "run", lambda *args, **kwargs: pytest.fail("process constructed"))
    with pytest.raises(PermissionError):
        actuator.run_shell(["python", "-c", code], cwd="link")
    assert effects == []


@pytest.mark.parametrize("cwd", ["missing", "plain", "/tmp", "..", "nested/../child", "bad\x00cwd", 7])
def test_invalid_cwd_has_zero_authorization_and_process(tmp_path, monkeypatch, cwd):
    sandbox, code = _write_marker(tmp_path, monkeypatch)
    (sandbox / "plain").write_text("not a directory")
    effects: list[bool] = []
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: effects.append(True))
    monkeypatch.setattr(actuator.subprocess, "run", lambda *args, **kwargs: pytest.fail("process constructed"))
    with pytest.raises((ValueError, PermissionError)):
        actuator.run_shell(["python", "-c", code], cwd=cwd)
    assert effects == []


def test_missing_sandbox_root_is_not_created(tmp_path, monkeypatch):
    sandbox, code = _write_marker(tmp_path, monkeypatch)
    sandbox.rmdir()
    effects: list[bool] = []
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: effects.append(True))
    with pytest.raises(PermissionError):
        actuator.run_shell(["python", "-c", code])
    assert effects == []
    assert not sandbox.exists()


def test_static_cwd_object_custody_verifier():
    verify(Path(actuator.__file__))


def test_parent_cwd_is_never_mutated(tmp_path, monkeypatch):
    parent_cwd = Path.cwd()
    sandbox, code = _write_marker(tmp_path, monkeypatch)
    (sandbox / "child").mkdir()
    actuator.run_shell(["python", "-c", code], cwd="child")
    assert Path.cwd() == parent_cwd
