from __future__ import annotations

import errno
import fcntl
import os
import shutil
import stat
import sys
from importlib import reload
from pathlib import Path

import pytest

from api import actuator
from scripts.verify_actuator_executable_object_custody import verify

pytestmark = [pytest.mark.no_legacy_skip, pytest.mark.skipif(sys.platform != "linux", reason="Linux memfd custody")]


def _literal(value: str) -> dict[str, object]:
    return {"type": "literal", "value": value}


def _ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, executable: Path | str, *arguments: str) -> None:
    reload(actuator)
    actuator.SANDBOX_DIR = tmp_path / "sandbox"
    actuator.SANDBOX_DIR.mkdir(exist_ok=True)
    actuator.WHITELIST = {"shell": [{
        "alias": "tool", "executable": str(executable),
        "arguments": [_literal(argument) for argument in arguments],
    }], "http": [], "timeout": 5}
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: None)


def _native(name: str) -> Path:
    path = shutil.which(name)
    assert path is not None
    resolved = Path(path).resolve()
    assert resolved.read_bytes()[:4] == b"\x7fELF"
    return resolved


def test_normal_native_snapshot_preserves_stdout_stderr_and_exit(tmp_path, monkeypatch):
    code = "import sys;print('out');print('err',file=sys.stderr);sys.exit(7)"
    _ready(tmp_path, monkeypatch, sys.executable, "-c", code)
    assert actuator.run_shell(["tool", "-c", code]) == {"code": 7, "stdout": "out\n", "stderr": "err\n"}


def test_authorization_time_native_path_replacement_executes_original_snapshot(tmp_path, monkeypatch):
    admitted = tmp_path / "admitted"
    replacement = tmp_path / "replacement"
    shutil.copy2(_native("true"), admitted)
    shutil.copy2(_native("false"), replacement)
    _ready(tmp_path, monkeypatch, admitted)
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: os.replace(replacement, admitted))
    result = actuator.run_shell(["tool"])
    assert result["code"] == 0
    assert admitted.read_bytes()[:4] == b"\x7fELF"


def test_authorization_time_same_inode_mutation_executes_original_snapshot(tmp_path, monkeypatch):
    admitted = tmp_path / "admitted"
    original = _native("true").read_bytes()
    attacker = _native("false").read_bytes()
    assert len(original) == len(attacker), "native fixture pair must support same-inode overwrite"
    admitted.write_bytes(original)
    admitted.chmod(0o755)
    inode = admitted.stat().st_ino
    _ready(tmp_path, monkeypatch, admitted)

    def mutate() -> None:
        with admitted.open("r+b", buffering=0) as stream:
            stream.write(attacker)
            os.fsync(stream.fileno())

    monkeypatch.setattr(actuator, "_authorize_effect", mutate)
    assert actuator.run_shell(["tool"])["code"] == 0
    assert admitted.stat().st_ino == inode


def test_source_unlink_permission_change_and_replacement_do_not_substitute(tmp_path, monkeypatch):
    admitted = tmp_path / "admitted"
    moved = tmp_path / "moved"
    shutil.copy2(_native("true"), admitted)
    _ready(tmp_path, monkeypatch, admitted)

    def replace() -> None:
        admitted.chmod(0)
        admitted.rename(moved)
        shutil.copy2(_native("false"), admitted)

    monkeypatch.setattr(actuator, "_authorize_effect", replace)
    assert actuator.run_shell(["tool"])["code"] == 0


def test_configured_symlink_is_canonicalized_and_retarget_cannot_change_invocation(tmp_path, monkeypatch):
    original = tmp_path / "original"
    attacker = tmp_path / "attacker"
    link = tmp_path / "tool-link"
    shutil.copy2(_native("true"), original)
    shutil.copy2(_native("false"), attacker)
    link.symlink_to(original)
    _ready(tmp_path, monkeypatch, link)

    def retarget() -> None:
        link.unlink()
        link.symlink_to(attacker)

    monkeypatch.setattr(actuator, "_authorize_effect", retarget)
    assert actuator.run_shell(["tool"])["code"] == 0


def test_sealed_snapshot_rejects_write_truncate_and_grow(tmp_path, monkeypatch):
    _ready(tmp_path, monkeypatch, _native("true"))
    snapshot = actuator._snapshot_executable(str(_native("true")))
    try:
        assert fcntl.fcntl(snapshot.fd, fcntl.F_GET_SEALS) & actuator._EXECUTABLE_SEALS == actuator._EXECUTABLE_SEALS
        for operation in (
            lambda: os.write(snapshot.fd, b"x"),
            lambda: os.ftruncate(snapshot.fd, 0),
            lambda: os.ftruncate(snapshot.fd, snapshot.size + 1),
        ):
            with pytest.raises(OSError) as caught:
                operation()
            assert caught.value.errno in {errno.EBADF, errno.EINVAL, errno.EPERM}
    finally:
        snapshot.close()


def test_shebang_script_is_denied_before_authorization_and_process(tmp_path, monkeypatch):
    script = tmp_path / "script"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    _ready(tmp_path, monkeypatch, script)
    effects: list[bool] = []
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: effects.append(True))
    monkeypatch.setattr(actuator.subprocess, "run", lambda *a, **k: pytest.fail("process constructed"))
    with pytest.raises(PermissionError, match="native ELF required"):
        actuator.run_shell(["tool"])
    assert effects == []


@pytest.mark.parametrize("kind", ["directory", "non_executable", "oversized"])
def test_malformed_executable_objects_are_denied_without_process(tmp_path, monkeypatch, kind):
    target = tmp_path / "target"
    if kind == "directory":
        target.mkdir()
    elif kind == "non_executable":
        target.write_bytes(b"\x7fELF")
        target.chmod(0o600)
    else:
        target.write_bytes(b"\x7fELF")
        target.chmod(0o700)
        with target.open("r+b") as stream:
            stream.truncate(actuator.MAX_EXECUTABLE_SNAPSHOT_BYTES + 1)
    _ready(tmp_path, monkeypatch, target)
    effects: list[bool] = []
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: effects.append(True))
    monkeypatch.setattr(actuator.subprocess, "run", lambda *a, **k: pytest.fail("process constructed"))
    with pytest.raises(PermissionError):
        actuator.run_shell(["tool"])
    assert effects == []


def test_static_executable_object_custody_verifier():
    verify(Path(actuator.__file__))
