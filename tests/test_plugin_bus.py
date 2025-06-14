"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import asyncio
import pytest
import plugin_bus


class DummyGUI:
    def __init__(self) -> None:
        self.panels = []

    def add_panel(self, panel) -> None:
        self.panels.append(panel)

    def refresh_plugins(self) -> None:
        pass


def test_placeholder(tmp_path):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / '__init__.py').write_text("", encoding='utf-8')
    plugin = plugins / "demo.py"
    plugin.write_text("VALUE='v1'\n\ndef register(gui): gui.add_panel(VALUE)\n", encoding="utf-8")

    gui = DummyGUI()
    bus = plugin_bus.PluginBus(gui, str(plugins))

    async def runner() -> None:
        task = asyncio.create_task(bus.watch_plugins())
        await asyncio.sleep(0.3)
        assert 'demo' in bus.modules
        assert gui.panels[-1] == 'v1'
        import time
        time.sleep(1.1)
        plugin.write_text("VALUE='v2'\n\ndef register(gui): gui.add_panel(VALUE)\n", encoding='utf-8')
        bus.load('demo')
        await asyncio.sleep(0.1)
        assert gui.panels[-1] == 'v2'
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(runner())
