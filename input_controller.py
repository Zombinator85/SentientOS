from logging_config import get_log_path
import os
import json
import datetime
import uuid
from pathlib import Path
from typing import Callable, Dict, Any, Optional, List, TYPE_CHECKING

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
if TYPE_CHECKING:  # pragma: no cover - for type hints
    from policy_engine import PolicyEngine

try:
    import pyautogui  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pyautogui = None

try:
    import keyboard  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    keyboard = None

# Unified event log shared with notification module
MEMORY_DIR = get_log_path("memory", "MEMORY_DIR")
EVENT_PATH = MEMORY_DIR / "events.jsonl"
EVENT_PATH.parent.mkdir(parents=True, exist_ok=True)

PANIC = False


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def _log(
    event: str,
    persona: Optional[str],
    backend: str,
    details: Dict[str, Any],
    *,
    status: str = "ok",
    error: Optional[str] = None,
    undo_id: Optional[str] = None,
    event_id: Optional[str] = None,
) -> str:
    event_id = event_id or uuid.uuid4().hex[:8]
    entry = {
        "id": event_id,
        "timestamp": _now(),
        "event": event,
        "persona": persona or "default",
        "backend": backend,
        "details": details,
        "status": status,
    }
    if error:
        entry["error"] = error
    if undo_id:
        entry["undo_id"] = undo_id
    with open(EVENT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return event_id


class BaseInputBackend:
    def type_text(self, text: str, target_window: Optional[str] = None) -> None:
        raise NotImplementedError


class DummyBackend(BaseInputBackend):
    def type_text(self, text: str, target_window: Optional[str] = None) -> None:
        print(f"[DUMMY] type '{text}' -> {target_window}")


class PyAutoGUIBackend(BaseInputBackend):
    def type_text(self, text: str, target_window: Optional[str] = None) -> None:
        if pyautogui is None:
            raise RuntimeError("pyautogui not available")
        pyautogui.write(text)


class KeyboardBackend(BaseInputBackend):
    def type_text(self, text: str, target_window: Optional[str] = None) -> None:
        if keyboard is None:
            raise RuntimeError("keyboard not available")
        keyboard.write(text)


BACKENDS: Dict[str, BaseInputBackend] = {
    "dummy": DummyBackend(),
}
if pyautogui:
    BACKENDS["pyautogui"] = PyAutoGUIBackend()
if keyboard:
    BACKENDS["keyboard"] = KeyboardBackend()


class InputController:
    def __init__(
        self,
        backend: str = "dummy",
        permission_callback: Optional[Callable[..., bool]] = None,
        policy_engine: Optional["PolicyEngine"] = None,
    ) -> None:
        self.backend = BACKENDS.get(backend, BACKENDS["dummy"])
        self.backend_name = backend
        self.permission_callback = permission_callback
        self.policy_engine = policy_engine
        self._history: List[tuple[str, Optional[str], Callable[[], None]]] = []

    def type_text(
        self,
        text: str,
        target_window: Optional[str] = None,
        persona: Optional[str] = None,
        log: bool = True,
        mentions: Optional[list[str]] = None,
    ) -> None:
        if PANIC:
            raise RuntimeError("Panic mode active")
        if self.permission_callback and not self.permission_callback(action="type_text", text=text, target_window=target_window):
            raise PermissionError("Permission denied")
        if self.policy_engine:
            actions = self.policy_engine.evaluate({"event": "input.type_text", "persona": persona})
            if any(a.get("type") == "deny" for a in actions):
                _log(
                    "input.type_text",
                    persona,
                    self.backend_name,
                    {"text": text, "target_window": target_window, "mentions": mentions or []},
                    status="failed",
                    error="policy_denied",
                )
                raise PermissionError("Policy denied")
        self.backend.type_text(text, target_window)
        undo_id = uuid.uuid4().hex[:8]
        self._history.append((undo_id, persona, lambda: self.backend.type_text("\b" * len(text), target_window)))
        if log:
            _log(
                "input.type_text",
                persona,
                self.backend_name,
                {"text": text, "target_window": target_window, "mentions": mentions or []},
                undo_id=undo_id,
            )

    def undo_last(self, persona: Optional[str] = None) -> bool:
        for i in range(len(self._history) - 1, -1, -1):
            uid, p, fn = self._history[i]
            if persona is None or p == persona:
                try:
                    fn()
                    _log("input.undo", p, self.backend_name, {"target": uid})
                    self._history.pop(i)
                    return True
                except Exception as e:  # pragma: no cover - defensive
                    _log(
                        "input.undo",
                        p,
                        self.backend_name,
                        {"target": uid},
                        status="failed",
                        error=str(e),
                    )
                    return False
        return False


def trigger_panic() -> None:
    global PANIC
    PANIC = True
    _log("panic", None, "system", {"state": "on"})


def reset_panic() -> None:
    global PANIC
    PANIC = False
    _log("panic", None, "system", {"state": "off"})


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Input controller CLI")
    parser.add_argument("--type")
    parser.add_argument("--persona")
    parser.add_argument("--backend", default="dummy")
    parser.add_argument("--panic", action="store_true", help="Trigger panic mode")
    parser.add_argument("--undo-last", action="store_true", help="Undo last action")
    args = parser.parse_args()

    if args.panic:
        trigger_panic()
        print("Panic triggered")
        return

    ic = InputController(backend=args.backend)
    if args.undo_last:
        if ic.undo_last(persona=args.persona):
            print("Undone")
        else:
            print("Nothing to undo")
        return
    ic.type_text(args.type, persona=args.persona)


if __name__ == "__main__":
    main()
