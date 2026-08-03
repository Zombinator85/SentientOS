from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


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


def test_actuator_import_has_no_privilege_or_runtime_effects(monkeypatch, tmp_path):
    monkeypatch.setenv("ACT_SANDBOX", str(tmp_path / "sandbox"))
    monkeypatch.setenv("ACT_PLUGINS_DIR", str(tmp_path / "plugins"))
    sys.modules.pop("api.actuator", None)
    module = importlib.import_module("api.actuator")
    assert not module.SANDBOX_DIR.exists()
    assert module.list_plugins() == {}
    assert module._worker_started is False


def test_actuator_protected_effects_authorize_before_execution(monkeypatch, tmp_path):
    import api.actuator as actuator
    events = []
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: events.append("authorize"))
    monkeypatch.setattr(actuator, "SANDBOX_DIR", tmp_path)
    actuator.file_write("proof.txt", "ok")
    assert events == ["authorize"]
    assert (tmp_path / "proof.txt").read_text() == "ok"


def test_external_plugins_require_explicit_initialization(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "plugins"; plugin_dir.mkdir()
    (plugin_dir / "sample.py").write_text('"""sample"""\ndef register(register):\n register("sample", object())\n')
    import api.actuator as actuator
    monkeypatch.setenv("ACT_PLUGINS_DIR", str(plugin_dir))
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: None)
    assert "sample" not in actuator.ACTUATORS
    actuator.initialize_actuators(load_external_plugins=True)
    assert "sample" in actuator.ACTUATORS
