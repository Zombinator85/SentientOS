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
import reflection_stream as rs


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

    def __init__(self, trigger: BaseTrigger, actions: List[Dict[str, Any]], name: str = "", preferred: bool = False) -> None:
        self.trigger = trigger
        self.actions = actions
        self.name = name
        self.preferred = preferred
        self.status = "preferred" if preferred else "candidate"

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

    EXPERIMENTS_FILE = Path(os.getenv("REFLEX_EXPERIMENTS", "logs/reflections/experiments.json"))

    def __init__(self, autopromote_trials: int = 5) -> None:
        self.rules: List[ReflexRule] = []
        self.experiments: Dict[str, Any] = {}
        self.history: List[Dict[str, Any]] = []
        self.autopromote_trials = autopromote_trials

    # ------------------------------------------------------------------
    def load_experiments(self) -> None:
        if self.EXPERIMENTS_FILE.exists():
            try:
                self.experiments = json.loads(self.EXPERIMENTS_FILE.read_text(encoding="utf-8"))
            except Exception:
                self.experiments = {}

    def save_experiments(self) -> None:
        self.EXPERIMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.EXPERIMENTS_FILE.write_text(json.dumps(self.experiments, indent=2), encoding="utf-8")

    def apply_analytics(self, analytics_data: Dict[str, Any]) -> None:
        """Create reflex rules based on workflow analytics."""
        usage = analytics_data.get("usage", {})
        for wf, info in usage.items():
            if info.get("failures", 0) >= 3:
                rule = ReflexRule(
                    OnDemandTrigger(),
                    [{"type": "workflow", "name": wf}],
                    name=f"retry_{wf}",
                )
                self.add_rule(rule)
                mm.append_memory(
                    json.dumps({"analysis": wf, "action": "retry"}),
                    tags=["reflex", "analytics"],
                    source="reflex",
                )

    def add_rule(self, rule: ReflexRule) -> None:
        self.rules.append(rule)

    def start(self) -> None:
        self.load_experiments()
        for r in self.rules:
            r.start()

    def propose_improvements(self, analytics_data: Dict[str, Any]) -> None:
        """Log reflex improvement proposals based on analytics."""
        usage = analytics_data.get("usage", {})
        for wf, info in usage.items():
            if info.get("fail_rate", 0) > 0.5:
                proposal = {"workflow": wf, "action": "retry"}
                rs.log_reflex_learn({"proposal": proposal})

    # ------------------------------------------------------------------
    def _record_result(self, exp: str, rule: ReflexRule, success: bool, duration: float) -> None:
        data = self.experiments.setdefault(exp, {"rules": {}, "history": []})
        rdata = data["rules"].setdefault(rule.name, {"trials": 0, "success": 0, "fail": 0, "durations": []})
        rdata["trials"] += 1
        rdata["durations"].append(duration)
        if success:
            rdata["success"] += 1
        else:
            rdata["fail"] += 1
        data["history"].append({"rule": rule.name, "success": success, "duration": duration})
        self.save_experiments()

        # auto promote if threshold reached
        if all(info.get("trials", 0) >= self.autopromote_trials for info in data["rules"].values()):
            self._auto_promote(exp)

    def _auto_promote(self, exp: str) -> None:
        data = self.experiments.get(exp)
        if not data:
            return
        rules = list(data["rules"].items())
        if len(rules) < 2:
            return
        # pick highest success rate
        winner = max(rules, key=lambda r: (r[1].get("success", 0) / max(1, r[1]["trials"])))
        winner_name = winner[0]
        self.promote_rule(winner_name, by="system", experiment=exp)
        for name, _ in rules:
            if name != winner_name:
                self.demote_rule(name, by="system", experiment=exp)
        data["status"] = "promoted"
        self.save_experiments()

    def ab_test(self, rule_a: ReflexRule, rule_b: ReflexRule) -> ReflexRule:
        """Execute two rules and log which succeeded."""
        results: Dict[str, str] = {}
        for rule in (rule_a, rule_b):
            start = time.time()
            try:
                rule.execute()
                results[rule.name] = "ok"
                success = True
            except Exception as e:  # pragma: no cover - defensive
                results[rule.name] = str(e)
                success = False
            duration = time.time() - start
            self._record_result(f"{rule_a.name}_vs_{rule_b.name}", rule, success, duration)
        rs.log_reflex_learn({"ab_test": [rule_a.name, rule_b.name], "results": results})
        return rule_a if results.get(rule_a.name) == "ok" else rule_b

    def promote_rule(self, name: str, by: str = "system", experiment: str | None = None) -> None:
        rule = next((r for r in self.rules if r.name == name), None)
        if not rule:
            return
        prev = rule.status
        rule.status = "preferred"
        rule.preferred = True
        self.history.append({"action": "promote", "rule": name, "by": by, "prev": prev})
        rs.log_reflex_learn({"promotion": name, "by": by, "experiment": experiment})
        rs.log_event("reflex", "promotion", by, name)
        self.save_experiments()

    def demote_rule(self, name: str, by: str = "system", experiment: str | None = None) -> None:
        rule = next((r for r in self.rules if r.name == name), None)
        if not rule:
            return
        prev = rule.status
        rule.status = "inactive"
        rule.preferred = False
        self.history.append({"action": "demote", "rule": name, "by": by, "prev": prev})
        rs.log_reflex_learn({"demotion": name, "by": by, "experiment": experiment})
        rs.log_event("reflex", "demotion", by, name)
        self.save_experiments()

    def revert_last(self) -> None:
        if not self.history:
            return
        last = self.history.pop()
        rule = next((r for r in self.rules if r.name == last.get("rule")), None)
        if rule:
            rule.status = last.get("prev", "candidate")
            rule.preferred = rule.status == "preferred"
            rs.log_reflex_learn({"revert": rule.name, "by": "system"})
            rs.log_event("reflex", "revert", "system", rule.name)
        self.save_experiments()

    def stop(self) -> None:
        panic_event.set()
        for r in self.rules:
            r.stop()
        self.save_experiments()


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
        rules.append(ReflexRule(trig, actions, name=item.get("name", ""), preferred=bool(item.get("preferred"))))
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
