from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import api.actuator as actuator
from scripts.verify_actuator_plugin_boundary import verify

pytestmark = pytest.mark.no_legacy_skip


BUILTINS = {"shell", "http", "file", "email", "webhook", "workflow", "talkback"}


def test_all_builtins_registered_and_initialization_is_idempotent() -> None:
    actuator.initialize_actuators()
    original = {name: actuator.ACTUATORS[name] for name in BUILTINS}
    actuator.initialize_actuators()
    assert set(actuator.BUILTIN_ACTUATOR_TYPES) == BUILTINS
    assert {name: actuator.ACTUATORS[name] for name in BUILTINS} == original


def test_builtin_file_actuator_functionality_is_unchanged(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(actuator, "SANDBOX_DIR", tmp_path)
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: None)
    assert actuator.dispatch({"type": "file", "path": "proof.txt", "content": "ok"}) == {
        "written": str(tmp_path / "proof.txt")
    }
    assert (tmp_path / "proof.txt").read_text(encoding="utf-8") == "ok"


def test_external_request_fails_before_registration_or_source_read(monkeypatch, tmp_path: Path) -> None:
    plugin = tmp_path / "sample.py"
    plugin.write_text('def register(callback): callback("sample", object())\n', encoding="utf-8")
    monkeypatch.setenv("ACT_PLUGINS_DIR", str(tmp_path))
    actuator.ACTUATORS.pop("sample", None)
    reads: list[Path] = []
    original_read_text = Path.read_text

    def watched_read_text(path: Path, *args: object, **kwargs: object) -> str:
        reads.append(path)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", watched_read_text)
    with pytest.raises(RuntimeError, match="external actuator plugins are disabled"):
        actuator.initialize_actuators(load_external_plugins=True)
    assert reads == []
    assert "sample" not in actuator.ACTUATORS


def test_configured_mixed_directory_has_zero_process_real_execution(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    marker = tmp_path / "executed"
    (plugins / "effect.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n", encoding="utf-8"
    )
    (plugins / "malformed.py").write_text("this is not valid Python !!!", encoding="utf-8")
    (plugins / "framework.py").write_text("import plugin_framework\n", encoding="utf-8")
    (plugins / "old_style.py").write_text(
        "def register(register_actuator):\n    register_actuator('external', object())\n", encoding="utf-8"
    )
    code = """
import api.actuator as actuator
assert 'external' not in actuator.ACTUATORS
actuator.initialize_actuators()
try:
    actuator.initialize_actuators(load_external_plugins=True)
except RuntimeError as exc:
    assert str(exc) == 'external actuator plugins are disabled'
else:
    raise AssertionError('external request did not fail closed')
assert 'external' not in actuator.ACTUATORS
"""
    env = os.environ.copy()
    env["ACT_PLUGINS_DIR"] = str(plugins)
    subprocess.run([sys.executable, "-c", code], cwd=Path.cwd(), env=env, check=True)
    assert not marker.exists()


def test_plugin_reload_surface_is_absent_and_cannot_delete_builtins() -> None:
    actuator.initialize_actuators()
    assert not hasattr(actuator, "reload_plugins")
    assert not hasattr(actuator, "load_plugins")
    assert "workflow" in actuator.ACTUATORS
    assert "talkback" in actuator.ACTUATORS


@pytest.mark.parametrize("argv", [["plugins"], ["shell", "--reload"]])
def test_cli_exposes_no_external_plugin_operation(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        actuator.main(argv)
    assert exc.value.code == 2


def test_static_verifier_proves_loader_and_reload_removal() -> None:
    result = verify()
    assert result == {
        "status": "actuator_plugin_boundary_ready",
        "path": "api/actuator.py",
        "violations": [],
    }
