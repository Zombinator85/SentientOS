from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

pytestmark = pytest.mark.no_legacy_skip


def _isolated_import(module: str, tmp_path: Path) -> dict[str, object]:
    code = dedent(
        """
        import importlib, json, os, pathlib, sys
        calls = []
        privilege = importlib.import_module("sentientos.privilege")
        privilege.require_admin_banner = lambda: calls.append("admin")
        privilege.require_lumos_approval = lambda: calls.append("lumos")
        sys.modules.pop("api.actuator", None)
        sys.modules.pop("api", None)
        module = importlib.import_module(sys.argv[1])
        paths = [os.environ["SENTIENTOS_LOG_DIR"], os.environ["ACT_SANDBOX"]]
        print(json.dumps({
            "calls": calls,
            "created": [path for path in paths if pathlib.Path(path).exists()],
            "plugins": getattr(module, "PLUGINS_INFO", {}),
            "worker": getattr(module, "_worker_started", False),
        }))
        """
    )
    env = os.environ.copy()
    env.update(
        SENTIENTOS_LOG_DIR=str(tmp_path / "logs"),
        ACT_SANDBOX=str(tmp_path / "sandbox"),
        ACT_PLUGINS_DIR=str(tmp_path / "plugins"),
        AUTONOMOUS_CALLS_LOG=str(tmp_path / "autonomous.jsonl"),
    )
    completed = subprocess.run(
        [sys.executable, "-c", code, module], env=env, text=True, capture_output=True, check=True
    )
    return json.loads(completed.stdout)


def test_scripts_lock_import_is_inert(monkeypatch):
    import sentientos.privilege as privilege
    calls = []
    monkeypatch.setattr(privilege, "require_admin_banner", lambda: calls.append("admin"))
    monkeypatch.setattr(privilege, "require_lumos_approval", lambda: calls.append("lumos"))
    sys.modules.pop("scripts.lock", None)
    importlib.import_module("scripts.lock")
    assert calls == []


def test_scripts_lock_check_is_unprivileged(monkeypatch, tmp_path):
    import scripts.lock as lock
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(lock, "LOCKS", ())
    monkeypatch.setattr(lock, "require_admin_banner", lambda: pytest.fail("authorization called"))
    monkeypatch.setattr(lock, "require_lumos_approval", lambda: pytest.fail("authorization called"))
    lock.check()


def test_scripts_lock_effects_authorize_before_mutation(monkeypatch):
    import scripts.lock as lock
    events = []
    monkeypatch.setattr(lock, "require_admin_banner", lambda: events.append("admin"))
    monkeypatch.setattr(lock, "require_lumos_approval", lambda: events.append("lumos"))
    monkeypatch.setattr(lock.subprocess, "check_call", lambda *_a, **_k: events.append("effect"))
    monkeypatch.setattr(lock, "LOCKS", ("lock",))
    lock.install()
    assert events[:3] == ["admin", "lumos", "effect"]


def test_api_package_import_is_inert(tmp_path):
    result = _isolated_import("api", tmp_path)
    assert result == {"calls": [], "created": [], "plugins": {}, "worker": False}


def test_actuator_import_has_no_privilege_or_runtime_effects(tmp_path):
    result = _isolated_import("api.actuator", tmp_path)
    assert result == {"calls": [], "created": [], "plugins": {}, "worker": False}


def test_actuator_import_does_not_create_log_directory(tmp_path):
    _isolated_import("api.actuator", tmp_path)
    assert not (tmp_path / "logs").exists()
    assert not (tmp_path / "autonomous.jsonl").exists()


def test_actuator_autonomous_log_directory_is_created_only_at_write_boundary(monkeypatch, tmp_path):
    import api.actuator as actuator

    autonomous_log = tmp_path / "nested" / "autonomous.jsonl"
    monkeypatch.setattr(actuator, "AUTONOMOUS_LOG", autonomous_log)
    monkeypatch.setattr(actuator, "act", lambda *_a, **_k: {})
    audit = type("Audit", (), {"log_entry": staticmethod(lambda **_kwargs: None)})
    monkeypatch.setitem(sys.modules, "autonomous_audit", audit)
    assert not autonomous_log.parent.exists()
    actuator.auto_call({"type": "proof"})
    assert autonomous_log.exists()


def test_actuator_protected_effects_authorize_before_execution(monkeypatch, tmp_path):
    import api.actuator as actuator
    events = []
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: events.append("authorize"))
    monkeypatch.setattr(actuator, "SANDBOX_DIR", tmp_path)
    actuator.file_write("proof.txt", "ok")
    assert events == ["authorize"]
    assert (tmp_path / "proof.txt").read_text() == "ok"


def test_external_plugins_are_rejected_without_execution(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "plugins"; plugin_dir.mkdir()
    marker = tmp_path / "marker"
    (plugin_dir / "sample.py").write_text(
        f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\n'
        'def register(register):\n register("sample", object())\n'
    )
    import api.actuator as actuator
    monkeypatch.setenv("ACT_PLUGINS_DIR", str(plugin_dir))
    assert "sample" not in actuator.ACTUATORS
    with pytest.raises(RuntimeError, match="external actuator plugins are disabled"):
        actuator.initialize_actuators(load_external_plugins=True)
    assert "sample" not in actuator.ACTUATORS
    assert not marker.exists()
