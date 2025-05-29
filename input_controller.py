import os
import json
import datetime
from pathlib import Path
from typing import Callable, Dict, Any, Optional

try:
    import pyautogui  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pyautogui = None

try:
    import keyboard  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    keyboard = None

# Unified event log shared with notification module
MEMORY_DIR = Path(os.getenv("MEMORY_DIR", "logs/memory"))
EVENT_PATH = MEMORY_DIR / "events.jsonl"
EVENT_PATH.parent.mkdir(parents=True, exist_ok=True)

PANIC = False


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def _log(event: str, persona: Optional[str], backend: str, details: Dict[str, Any]) -> None:
    entry = {
        "timestamp": _now(),
        "event": event,
        "persona": persona or "default",
        "backend": backend,
        "details": details,
    }
    with open(EVENT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


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
    def __init__(self, backend: str = "dummy", permission_callback: Optional[Callable[..., bool]] = None):
        self.backend = BACKENDS.get(backend, BACKENDS["dummy"])
        self.backend_name = backend
        self.permission_callback = permission_callback

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
        self.backend.type_text(text, target_window)
        if log:
            _log(
                "input.type_text",
                persona,
                self.backend_name,
                {"text": text, "target_window": target_window, "mentions": mentions or []},
            )


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
    args = parser.parse_args()

    if args.panic:
        trigger_panic()
        print("Panic triggered")
        return

    ic = InputController(backend=args.backend)
    ic.type_text(args.type, persona=args.persona)


if __name__ == "__main__":
    main()
