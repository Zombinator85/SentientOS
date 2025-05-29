import os
import json
import datetime
from pathlib import Path
from typing import Callable, Dict, Any, Optional

try:
    from pywinauto.application import Application  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Application = None

try:
    import uiautomation as auto  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    auto = None

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


class BaseUIBackend:
    def click_button(self, label: str, window: Optional[str] = None) -> None:
        raise NotImplementedError


class DummyUIBackend(BaseUIBackend):
    def click_button(self, label: str, window: Optional[str] = None) -> None:
        print(f"[DUMMY] click '{label}' -> {window}")


class PyWinAutoBackend(BaseUIBackend):
    def click_button(self, label: str, window: Optional[str] = None) -> None:
        if Application is None:
            raise RuntimeError("pywinauto not available")
        if window:
            app = Application().connect(title=window)
            dlg = app.window(title=window)
            dlg[label].click()
        else:
            raise RuntimeError("window required for pywinauto backend")


class UIAutomationBackend(BaseUIBackend):
    def click_button(self, label: str, window: Optional[str] = None) -> None:
        if auto is None:
            raise RuntimeError("uiautomation not available")
        ctrl = auto.WindowControl(searchDepth=1, Name=window) if window else auto.ControlFromCursor()
        btn = ctrl.ButtonControl(Name=label)
        btn.Click()


BACKENDS: Dict[str, BaseUIBackend] = {
    "dummy": DummyUIBackend(),
}
if Application:
    BACKENDS["pywinauto"] = PyWinAutoBackend()
if auto:
    BACKENDS["uiautomation"] = UIAutomationBackend()


class UIController:
    def __init__(self, backend: str = "dummy", permission_callback: Optional[Callable[..., bool]] = None):
        self.backend = BACKENDS.get(backend, BACKENDS["dummy"])
        self.backend_name = backend
        self.permission_callback = permission_callback

    def click_button(
        self,
        label: str,
        window: Optional[str] = None,
        persona: Optional[str] = None,
        log: bool = True,
        mentions: Optional[list[str]] = None,
    ) -> None:
        if PANIC:
            raise RuntimeError("Panic mode active")
        if self.permission_callback and not self.permission_callback(action="click_button", label=label, window=window):
            raise PermissionError("Permission denied")
        self.backend.click_button(label, window)
        if log:
            _log(
                "ui.click_button",
                persona,
                self.backend_name,
                {"label": label, "window": window, "mentions": mentions or []},
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

    parser = argparse.ArgumentParser(description="UI controller CLI")
    parser.add_argument("--click")
    parser.add_argument("--window")
    parser.add_argument("--persona")
    parser.add_argument("--backend", default="dummy")
    parser.add_argument("--panic", action="store_true")
    args = parser.parse_args()

    if args.panic:
        trigger_panic()
        print("Panic triggered")
        return

    uc = UIController(backend=args.backend)
    uc.click_button(args.click, window=args.window, persona=args.persona)


if __name__ == "__main__":
    main()
