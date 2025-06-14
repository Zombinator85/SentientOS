"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()

"""Bridge reacting to :class:`Turn` emotions with lighting and facial cues."""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict

import yaml  # type: ignore[import-untyped]  # optional dependency
from sentientos.parliament_bus import ParliamentBus, Turn


class EmotionBridge:
    """Subscribe to a :class:`ParliamentBus` and react to turn emotions."""

    def __init__(self, bus: ParliamentBus, map_path: Path | str = "emotion_map.yaml") -> None:
        self.bus = bus
        self.map_path = Path(map_path)
        self.emotion_map = self._load_map(self.map_path)
        self.enable_light_sync = True
        self.enable_face_sync = True

    def _load_map(self, path: Path) -> Dict[str, Dict[str, str]]:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                out: Dict[str, Dict[str, str]] = {}
                for key, val in data.items():
                    if isinstance(val, dict):
                        color = str(val.get("color", ""))
                        face = str(val.get("face", ""))
                        out[str(key)] = {"color": color, "face": face}
                return out
        except Exception:
            pass
        return {}

    async def run(self) -> None:
        """Continuously react to incoming turns."""
        async for turn in self.bus.subscribe():
            await self.react_to(turn)

    async def react_to(self, turn: Turn) -> None:
        """Trigger lighting and face cues for ``turn``."""
        emotion = turn.emotion or "neutral"
        config = self.emotion_map.get(emotion) or self.emotion_map.get("neutral")
        if not config:
            return
        color = config.get("color")
        face = config.get("face")
        if self.enable_light_sync and color:
            self._set_light(color)
        if self.enable_face_sync and face:
            self._animate_face(face)

    def _set_light(self, color: str) -> None:
        # Placeholder for Philips Hue or DMX control
        print("Set light:", color)

    def _animate_face(self, code: str) -> None:
        # Placeholder for facial animation sync
        Path("/tmp/face_sync.json").write_text(json.dumps({"expression": code}))
        print("Animate face:", code)


def main() -> None:  # pragma: no cover - simple runner
    bus = ParliamentBus()
    bridge = EmotionBridge(bus)
    asyncio.run(bridge.run())


if __name__ == "__main__":  # pragma: no cover
    main()
