from logging_config import get_log_path
import os
import json
import datetime
import uuid
from pathlib import Path
from typing import Callable, Dict, Any, Optional, List, TYPE_CHECKING

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
if TYPE_CHECKING:  # pragma: no cover
    from policy_engine import PolicyEngine

try:
    from pywinauto.application import Application  # type: ignore  # Windows UI automation
except Exception:  # pragma: no cover - optional dependency
    Application = None

try:
    import uiautomation as auto  # type: ignore  # uiautomation lacks stubs
except Exception:  # pragma: no cover - optional dependency
    auto = None

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
        if self.policy_engine:
            actions = self.policy_engine.evaluate({"event": "ui.click_button", "persona": persona})
            if any(a.get("type") == "deny" for a in actions):
                _log(
                    "ui.click_button",
                    persona,
                    self.backend_name,
                    {"label": label, "window": window, "mentions": mentions or []},
                    status="failed",
                    error="policy_denied",
                )
                raise PermissionError("Policy denied")
        self.backend.click_button(label, window)
        undo_id = uuid.uuid4().hex[:8]
        self._history.append((undo_id, persona, lambda: None))
        if log:
            _log(
                "ui.click_button",
                persona,
                self.backend_name,
                {"label": label, "window": window, "mentions": mentions or []},
                undo_id=undo_id,
            )

    def undo_last(self, persona: Optional[str] = None) -> bool:
        for i in range(len(self._history) - 1, -1, -1):
            uid, p, fn = self._history[i]
            if persona is None or p == persona:
                try:
                    fn()
                    _log("ui.undo", p, self.backend_name, {"target": uid})
                    self._history.pop(i)
                    return True
                except Exception as e:  # pragma: no cover
                    _log(
                        "ui.undo",
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

    parser = argparse.ArgumentParser(description="UI controller CLI")
    parser.add_argument("--click")
    parser.add_argument("--window")
    parser.add_argument("--persona")
    parser.add_argument("--backend", default="dummy")
    parser.add_argument("--panic", action="store_true")
    parser.add_argument("--undo-last", action="store_true")
    args = parser.parse_args()

    if args.panic:
        trigger_panic()
        print("Panic triggered")
        return

    uc = UIController(backend=args.backend)
    if args.undo_last:
        if uc.undo_last(persona=args.persona):
            print("Undone")
        else:
            print("Nothing to undo")
        return
    uc.click_button(args.click, window=args.window, persona=args.persona)


if __name__ == "__main__":
    main()
