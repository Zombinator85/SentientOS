"""Policy-aware GUI control shim."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional

import affective_context as ac
from sentientos.autonomy.audit import AutonomyActionLogger
from sentientos.sensor_provenance import default_provenance_for_constraint


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
        audit_logger: AutonomyActionLogger | None = None,
    ) -> None:
        self._config = config
        self._mouse_driver = mouse_driver or (lambda action, payload: None)
        self._keyboard_driver = keyboard_driver or (lambda action, payload: None)
        self._panic_flag = panic_flag or (lambda: False)
        self._audit = audit_logger

    @property
    def enabled(self) -> bool:
        return self._config.enable and not self._panic_flag()

    def click(self, *, x: int, y: int, button: str = "left") -> None:
        self._require_enabled("click", {"x": x, "y": y, "button": button})
        payload = {"x": int(x), "y": int(y), "button": button}
        self._mouse_driver("click", payload)
        self._log("click", "performed", payload)

    def move(self, *, x: int, y: int) -> None:
        self._require_enabled("move", {"x": x, "y": y})
        payload = {"x": int(x), "y": int(y), "smooth": self._config.move_smoothing}
        self._mouse_driver("move", payload)
        self._log("move", "performed", payload)

    def type_text(self, text: str, *, delay: float | None = None) -> None:
        self._require_enabled("type", {"text": text, "delay": delay})
        if self._config.safety != "permissive" and self._looks_sensitive(text):
            self._log("type", "blocked", {"reason": "safety_policy"})
            raise GUIControlError("typing rejected by safety policy")
        payload = {"text": text, "delay": delay}
        self._keyboard_driver("type", payload)
        self._log("type", "performed", payload)

    def focus_window(self, title: str) -> None:
        self._require_enabled("focus", {"title": title})
        self._mouse_driver("focus", {"title": title})
        self._log("focus", "performed", {"title": title})

    def _looks_sensitive(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in lowered for token in {"password", "secret", "token"})

    def _require_enabled(self, action: str, payload: Mapping[str, object] | None = None) -> None:
        if not self.enabled:
            reason = "panic" if self._panic_flag() else "disabled"
            self._log(action, "blocked", {"reason": reason, **(payload or {})})
            raise GUIControlError("GUI control disabled or panic active")

    def _log(self, action: str, status: str, payload: Mapping[str, object] | None = None) -> None:
        if not self._audit:
            return
        details = dict(payload or {})
        overlay = ac.capture_affective_context(
            "gui_control",
            overlay={
                "blocked": 1.0 if status == "blocked" else 0.2,
                "precision": 0.6 if action == "move" else 0.4,
            },
        )
        constraint_id = f"autonomy::gui::{action}"
        provenance = default_provenance_for_constraint(constraint_id)
        assumptions = ("panic_guard_respected", f"safety_mode={self._config.safety}")
        environment = {"panic": bool(self._panic_flag()), **details}
        self._audit.log(
            "gui",
            action,
            status,
            affective_overlay=overlay,
            constraint_id=constraint_id,
            constraint_justification="GUI control must remain affective, explainable, and constraint-referenced",
            sensor_provenance=provenance,
            assumptions=assumptions,
            environment=environment,
            pressure_reason=details.get("reason", status),
            **details,
        )

    def status(self) -> Mapping[str, object]:
        return {
            "status": "healthy" if self.enabled else "disabled",
            "mode": self._config.safety,
            "move_smoothing": self._config.move_smoothing,
        }


__all__ = ["GUIConfig", "GUIController", "GUIControlError"]
