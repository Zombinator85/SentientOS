require_admin_banner()
require_lumos_approval()

import asyncio
from pathlib import Path
from sentientos.parliament_bus import ParliamentBus, Turn
import emotion_bridge as eb


def test_react_to_mapping(tmp_path, capsys):
    mapping = tmp_path / "map.yaml"
    mapping.write_text("happy:\n  color: '#00FF00'\n  face: grin\nneutral:\n  color: '#FFFFFF'\n  face: neutral\n")
    bus = ParliamentBus()
    bridge = eb.EmotionBridge(bus, map_path=mapping)
    turn = Turn("a", "hi", emotion="happy")
    asyncio.run(bridge.react_to(turn))
    out = capsys.readouterr().out
    assert "Set light: #00FF00" in out
    assert "Animate face: grin" in out


def test_react_to_fallback(tmp_path, capsys):
    mapping = tmp_path / "map.yaml"
    mapping.write_text("neutral:\n  color: '#FFFFFF'\n  face: neutral\n")
    bus = ParliamentBus()
    bridge = eb.EmotionBridge(bus, map_path=mapping)
    turn = Turn("b", "hi", emotion="unknown")
    asyncio.run(bridge.react_to(turn))
    out = capsys.readouterr().out
    assert "Set light: #FFFFFF" in out
    assert "Animate face: neutral" in out
