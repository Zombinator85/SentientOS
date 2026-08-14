"""Regression coverage for the retired root filesystem plugin bus."""
from __future__ import annotations

import asyncio

import plugin_bus


class DummyGUI:
    def __init__(self) -> None:
        self.panels: list[object] = []
        self.refresh_count = 0

    def refresh_plugins(self) -> None:
        self.refresh_count += 1


def test_configured_directory_source_and_changes_have_zero_execution(tmp_path) -> None:
    directory = tmp_path / "plugins"
    marker = tmp_path / "marker"
    directory.mkdir()
    source = directory / "demo.py"
    source.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n", encoding="utf-8")

    gui = DummyGUI()
    bus = plugin_bus.PluginBus(gui, str(directory))
    bus.load("demo")
    bus.load_all()
    asyncio.run(bus.watch_plugins())
    source.write_text("this is malformed Python !!!", encoding="utf-8")
    bus.load("demo")

    assert not marker.exists()
    assert bus.modules == {}


def test_deliberate_internal_registration_refreshes_gui() -> None:
    gui = DummyGUI()
    bus = plugin_bus.PluginBus(gui)
    admitted = object()

    bus.register("internal", admitted)

    assert bus.modules == {"internal": admitted}
    assert gui.refresh_count == 1
