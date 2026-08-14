"""Executable proof that legacy loaders confer no external source authority."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import plugin_bus
from scripts.verify_legacy_extension_source_boundary import verify
from sentientos import plugin_loader


class DummyGUI:
    def __init__(self) -> None:
        self.refreshes = 0

    def refresh_plugins(self) -> None:
        self.refreshes += 1

    def update(self) -> None:
        self.refreshes += 1


def _hostile_sources(directory: Path, marker: Path) -> None:
    directory.mkdir()
    marker_write = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    sources = {
        "top_level.py": marker_write,
        "malformed.py": "def broken(:\n",
        "register.py": "def register(gui): gui.registered = True\n",
        "trusted_true.py": "TRUSTED = True\n" + marker_write,
        "trusted_false.py": "TRUSTED = False\n" + marker_write,
        "raises.py": "raise RuntimeError('executed')\n",
        "pycall.py": marker_write + "def register(gui): gui.pycall = True\n",
    }
    for name, source in sources.items():
        (directory / name).write_text(source, encoding="utf-8")


def test_process_real_hostile_directory_has_zero_execution(tmp_path) -> None:
    """Exercise both loaders in a fresh interpreter against hostile real files."""
    directory = tmp_path / "plugins"
    marker = tmp_path / "marker"
    _hostile_sources(directory, marker)
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import asyncio, json, plugin_bus\n"
        "from sentientos.plugin_loader import PluginLoader, main\n"
        "class G:\n"
        "  def refresh_plugins(self): pass\n"
        "  def update(self): pass\n"
        f"d={str(directory)!r}\n"
        "g=G(); b=plugin_bus.PluginBus(g,d); b.load('top_level'); b.load_all(); asyncio.run(b.watch_plugins())\n"
        "p=PluginLoader(g,d); p._start(); p._load_existing(); p._load_plugin('trusted_true'); p._handle(type('E',(),{'src_path':d+'/pycall.py'})()); p.set_trusted_only(False); p.stop()\n"
        "main(['--list']); main([])\n"
        "print(json.dumps({'root':list(b.modules), 'packaged':p.active_plugins(), 'errors':p.error_log()}))\n",
        encoding="utf-8",
    )
    env = dict(os.environ, PYTHONPATH=str(Path.cwd()))
    result = subprocess.run([sys.executable, str(probe)], cwd=tmp_path, env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    state = json.loads(result.stdout.strip().splitlines()[-1])
    assert state == {"root": [], "packaged": [], "errors": {}}


def test_filesystem_create_modify_events_have_zero_effect(tmp_path) -> None:
    directory = tmp_path / "plugins"
    marker = tmp_path / "marker"
    gui = DummyGUI()
    root_bus = plugin_bus.PluginBus(gui, str(directory))
    packaged = plugin_loader.PluginLoader(gui, str(directory))
    directory.mkdir()
    source = directory / "created.py"
    source.write_text(f"open({str(marker)!r}, 'w').write('created')", encoding="utf-8")
    packaged._handle(type("Event", (), {"src_path": str(source)})())
    source.write_text(f"open({str(marker)!r}, 'w').write('modified')", encoding="utf-8")
    packaged._handle(type("Event", (), {"src_path": str(source)})())
    root_bus.load("created")

    assert not marker.exists()
    assert packaged.active_plugins() == []
    assert root_bus.modules == {}


def test_installed_entry_point_load_has_zero_execution(monkeypatch) -> None:
    called = False

    def hostile_entry_points(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("entry-point metadata was enumerated")

    monkeypatch.setattr("importlib.metadata.entry_points", hostile_entry_points)
    bus = plugin_loader.PluginBus()
    assert tuple(plugin_loader.load_plugins(bus)) == ()
    assert tuple(plugin_loader.load_plugins(bus, load=False)) == ()
    plugin_loader.main(["--list"])
    assert not called
    assert bus.plugins == {}


def test_packaged_internal_registration_and_status_cli(capsys) -> None:
    bus = plugin_loader.PluginBus()
    admitted = object()
    bus.register("internal", admitted)
    plugin_loader.main([])
    assert bus.plugins == {"internal": admitted}
    assert plugin_loader.RETIRED_MESSAGE in capsys.readouterr().out


def test_static_legacy_extension_source_boundary() -> None:
    assert verify() == []
