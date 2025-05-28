import os
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

try:
    from watchdog.observers import Observer  # type: ignore
    from watchdog.events import FileSystemEventHandler  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Observer = None  # type: ignore
    FileSystemEventHandler = object  # type: ignore

from api import actuator
import memory_manager as mm


panic_event = threading.Event()


class BaseTrigger:
    """Interface for triggers."""

    def start(self, callback: Callable[[], None]) -> None:
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - optional
        pass


class IntervalTrigger(BaseTrigger):
    """Trigger that fires periodically."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._stop = threading.Event()

    def start(self, callback: Callable[[], None]) -> None:
        def loop() -> None:
            while not self._stop.is_set() and not panic_event.is_set():
                time.sleep(self.seconds)
                if not panic_event.is_set():
                    callback()

        threading.Thread(target=loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


class OnDemandTrigger(BaseTrigger):
    """Trigger invoked manually via ``fire``."""

    def start(self, callback: Callable[[], None]) -> None:
        self._callback = callback

    def fire(self) -> None:
        if hasattr(self, "_callback") and not panic_event.is_set():
            self._callback()


class FileChangeTrigger(BaseTrigger):
    """Trigger when files under a path change."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.observer: Observer | None = None

    def start(self, callback: Callable[[], None]) -> None:
        if Observer is None:  # pragma: no cover - missing watchdog
            raise RuntimeError("watchdog not installed")

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event) -> None:  # type: ignore[override]
                if not panic_event.is_set():
                    callback()

        self.observer = Observer()
        self.observer.schedule(Handler(), str(self.path), recursive=True)
        self.observer.start()

    def stop(self) -> None:  # pragma: no cover - simple
        if self.observer:
            self.observer.stop()
            self.observer.join()


class ReflexRule:
    """Couples a trigger with one or more actuator intents."""

    def __init__(self, trigger: BaseTrigger, actions: List[Dict[str, Any]], name: str = "") -> None:
        self.trigger = trigger
        self.actions = actions
        self.name = name

    def start(self) -> None:
        self.trigger.start(self.execute)

    def stop(self) -> None:
        self.trigger.stop()

    def execute(self) -> None:
        if panic_event.is_set():
            return
        for action in self.actions:
            try:
                actuator.act(action)
            except Exception as e:  # pragma: no cover - defensive
                mm.append_memory(
                    json.dumps({"error": str(e), "intent": action}),
                    tags=["reflex", "error"],
                    source="reflex",
                )


class ReflexManager:
    """Manage a collection of reflex rules."""

    def __init__(self) -> None:
        self.rules: List[ReflexRule] = []

    def add_rule(self, rule: ReflexRule) -> None:
        self.rules.append(rule)

    def start(self) -> None:
        for r in self.rules:
            r.start()

    def stop(self) -> None:
        panic_event.set()
        for r in self.rules:
            r.stop()


# --- Helpers -----------------------------------------------------------------

def load_rules(path: str) -> List[ReflexRule]:
    """Load reflex rules from a JSON or YAML file."""
    p = Path(path)
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
    except Exception:
        data = json.loads(text)
    rules: List[ReflexRule] = []
    for item in data:
        trig_type = item.get("trigger")
        if trig_type == "interval":
            trig = IntervalTrigger(float(item.get("seconds", 60)))
        elif trig_type == "file_change":
            trig = FileChangeTrigger(item.get("path", "."))
        elif trig_type == "on_demand":
            trig = OnDemandTrigger()
        else:
            continue
        actions = item.get("actions", [])
        rules.append(ReflexRule(trig, actions, name=item.get("name", "")))
    return rules


if __name__ == "__main__":  # pragma: no cover - CLI usage
    import argparse

    parser = argparse.ArgumentParser(description="Run reflex routines")
    parser.add_argument("config", help="Path to reflex config (JSON/YAML)")
    args = parser.parse_args()

    mgr = ReflexManager()
    for r in load_rules(args.config):
        mgr.add_rule(r)
    print(f"Loaded {len(mgr.rules)} rules")
    mgr.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
        mgr.stop()
