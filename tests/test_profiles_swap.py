"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
from pathlib import Path
import importlib
import profile_manager as pm
import sentient_banner as sb


def test_placeholder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    importlib.reload(pm)
    monkeypatch.setattr(pm, "PROFILES_DIR", tmp_path / "profiles", raising=False)
    pm.PROFILES_DIR.mkdir()
    monkeypatch.setattr(pm, "CURRENT_FILE", pm.PROFILES_DIR / ".current", raising=False)
    monkeypatch.setattr(pm, "HOME_CURRENT", tmp_path / ".sentientos_profile", raising=False)

    called = {"flush": 0, "restart": 0, "profile": None}
    monkeypatch.setattr(pm, "flush_agents", lambda: called.__setitem__("flush", called["flush"] + 1))
    monkeypatch.setattr(pm, "restart_bridges", lambda: called.__setitem__("restart", called["restart"] + 1))
    monkeypatch.setattr(sb, "set_current_profile", lambda name: called.__setitem__("profile", name), raising=False)

    pm.create_profile("a")
    pm.create_profile("b")

    pm.switch_profile("a")
    env_a = os.environ["MEMORY_DIR"]

    pm.switch_profile("b")
    env_b = os.environ["MEMORY_DIR"]

    assert env_a != env_b
    assert called["profile"] == "b"
    assert called["flush"] == 2
    assert called["restart"] == 2
    assert Path(pm.HOME_CURRENT).read_text().strip() == "b"
