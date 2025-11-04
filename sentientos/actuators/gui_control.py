"""Policy-aware GUI control shim."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional


@dataclass
class GUIConfig:
    enable: bool = False
    safety: str = "standard"
    move_smoothing: bool = True


class GUIControlError(RuntimeError):
    pass


class GUIController:
    def __init__(
        self,
        config: GUIConfig,
        *,
        mouse_driver: Callable[[str, Mapping[str, object]], None] | None = None,
        keyboard_driver: Callable[[str, Mapping[str, object]], None] | None = None,
        panic_flag: Callable[[], bool] | None = None,
    ) -> None:
        self._config = config
        self._mouse_driver = mouse_driver or (lambda action, payload: None)
        self._keyboard_driver = keyboard_driver or (lambda action, payload: None)
        self._panic_flag = panic_flag or (lambda: False)

    @property
    def enabled(self) -> bool:
        return self._config.enable and not self._panic_flag()

    def click(self, *, x: int, y: int, button: str = "left") -> None:
        self._require_enabled()
        payload = {"x": int(x), "y": int(y), "button": button}
        self._mouse_driver("click", payload)

    def move(self, *, x: int, y: int) -> None:
        self._require_enabled()
        payload = {"x": int(x), "y": int(y), "smooth": self._config.move_smoothing}
        self._mouse_driver("move", payload)

    def type_text(self, text: str, *, delay: float | None = None) -> None:
        self._require_enabled()
        if self._config.safety != "permissive" and self._looks_sensitive(text):
            raise GUIControlError("typing rejected by safety policy")
        payload = {"text": text, "delay": delay}
        self._keyboard_driver("type", payload)

    def focus_window(self, title: str) -> None:
        self._require_enabled()
        self._mouse_driver("focus", {"title": title})

    def _looks_sensitive(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in {"password", "secret", "token"})

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise GUIControlError("GUI control disabled or panic active")

    def status(self) -> Mapping[str, object]:
        return {
            "status": "healthy" if self.enabled else "disabled",
            "mode": self._config.safety,
            "move_smoothing": self._config.move_smoothing,
        }


__all__ = ["GUIConfig", "GUIController", "GUIControlError"]

