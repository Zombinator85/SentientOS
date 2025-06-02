from __future__ import annotations
from logging_config import get_log_path

import os
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import datetime

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
try:
    from watchdog.observers import Observer  # type: ignore
    from watchdog.events import FileSystemEventHandler  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Observer = None  # type: ignore
    FileSystemEventHandler = object  # type: ignore

from api import actuator
import memory_manager as mm
import reflection_stream as rs
import final_approval
import autonomous_audit as aa
from ritual import check_master_files

DEFAULT_MANAGER: "ReflexManager | None" = None

def set_default_manager(manager: "ReflexManager") -> None:
    global DEFAULT_MANAGER
    DEFAULT_MANAGER = manager

def get_default_manager() -> "ReflexManager | None":
    return DEFAULT_MANAGER

def default_manager() -> "ReflexManager":
    mgr = get_default_manager()
    if mgr is None:
        mgr = ReflexManager()
        set_default_manager(mgr)
    return mgr


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

    def fire(self, agent: str | None = None, persona: str | None = None) -> None:
        if hasattr(self, "_callback") and not panic_event.is_set():
            self._callback(agent=agent, persona=persona)


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


class ConditionalTrigger(BaseTrigger):
    """Trigger when a custom check function returns True."""

    def __init__(self, check: Callable[[], bool], interval: float = 1.0) -> None:
        self.check = check
        self.interval = interval
        self._stop = threading.Event()

    def start(self, callback: Callable[[], None]) -> None:
        def loop() -> None:
            while not self._stop.is_set() and not panic_event.is_set():
                if self.check() and not panic_event.is_set():
                    callback()
                time.sleep(self.interval)

        threading.Thread(target=loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


class ReflexRule:
    """Couples a trigger with one or more actuator intents."""

    def __init__(self, trigger: BaseTrigger, actions: List[Dict[str, Any]], name: str = "", preferred: bool = False, frozen: bool = False) -> None:
        self.trigger = trigger
        self.actions = actions
        self.name = name
        self.preferred = preferred
        self.status = "preferred" if preferred else "candidate"
        self.manager: "ReflexManager | None" = None
        self.frozen = frozen

    def start(self) -> None:
        self.trigger.start(self.execute)

    def stop(self) -> None:
        self.trigger.stop()

    def execute(self, agent: str | None = None, persona: str | None = None) -> bool:
        if panic_event.is_set():
            return False
        ok, missing = check_master_files()
        if not ok:
            aa.log_entry(
                action="refusal",
                rationale="sanctity violation",
                source={"missing": missing},
                expected="abort",
                why_chain=[f"Rule '{self.name}' refused due to missing master files"],
                agent=agent or "auto",
            )
            return False
        success = True
        start = time.time()
        for action in self.actions:
            try:
                result = actuator.act(action)
                mem = []
                if isinstance(result, dict) and result.get("log_id"):
                    mem.append(result["log_id"])
                aa.log_entry(
                    action=json.dumps(action),
                    rationale=f"rule {self.name}",
                    memory=mem,
                    expected=str(result),
                    why_chain=[
                        f"Action triggered because rule '{self.name}' fired",
                        f"Rule '{self.name}' present for automation",
                        "Fragment relevant because event triggered rule",
                    ],
                    agent=agent or "auto",
                )
            except Exception as e:  # pragma: no cover - defensive
                success = False
                mm.append_memory(
                    json.dumps({"error": str(e), "intent": action}),
                    tags=["reflex", "error"],
                    source="reflex",
                )
        duration = time.time() - start
        if self.manager:
            self.manager.record_trial(self, success, duration, agent=agent, persona=persona)
        return success

class ReflexManager:
    """Manage a collection of reflex rules."""

    EXPERIMENTS_FILE = get_log_path("reflections/experiments.json", "REFLEX_EXPERIMENTS")
    TRIAL_LOG = get_log_path("reflections/reflex_trials.jsonl", "REFLEX_TRIAL_LOG")
    AUDIT_LOG = get_log_path("reflections/reflex_audit.jsonl", "REFLEX_AUDIT_LOG")

    def __init__(self, autopromote_trials: int = 5) -> None:
        self.rules: List[ReflexRule] = []
        self.experiments: Dict[str, Any] = {}
        self.history: List[Dict[str, Any]] = []
        self.autopromote_trials = autopromote_trials
        self.TRIAL_LOG.parent.mkdir(parents=True, exist_ok=True)
        self.AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        self.audit: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    def _audit(
        self,
        action: str,
        rule: str,
        *,
        by: str = "system",
        persona: Optional[str] = None,
        experiment: Optional[str] = None,
        comment: str = "",
        policy: Optional[str] = None,
        reviewer: Optional[str] = None,
        tags: Optional[List[str]] = None,
        prev: Optional[str] = None,
        current: Optional[str] = None,
    ) -> None:
        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "action": action,
            "rule": rule,
            "by": by,
            "persona": persona,
            "experiment": experiment,
            "comment": comment,
            "policy": policy,
            "reviewer": reviewer,
            "tags": tags or [],
        }
        if prev is not None:
            entry["prev"] = prev
        if current is not None:
            entry["current"] = current
        self.audit.append(entry)
        with self.AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

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

    def annotate(
        self,
        rule: str,
        comment: str,
        *,
        tags: Optional[List[str]] = None,
        by: str = "user",
        persona: Optional[str] = None,
        experiment: Optional[str] = None,
        policy: Optional[str] = None,
        reviewer: Optional[str] = None,
    ) -> None:
        """Add an annotation/comment to a reflex experiment."""
        self._audit(
            "annotate",
            rule,
            by=by,
            persona=persona,
            experiment=experiment,
            comment=comment,
            policy=policy,
            reviewer=reviewer,
            tags=tags,
        )

    # ------------------------------------------------------------------
    def auto_generate_rule(
        self,
        trigger: BaseTrigger,
        actions: List[Dict[str, Any]],
        name: str,
        *,
        signals: Optional[Dict[str, Any]] = None,
    ) -> ReflexRule:
        """Create and start a rule from autonomous analysis."""
        rule = ReflexRule(trigger, actions, name=name)
        self.add_rule(rule)
        rule.start()
        self._audit("auto_rule", name, by="auto", comment=json.dumps(signals or {}))
        return rule

    def auto_prune(self, min_success: float = 0.2, min_trials: int = 5) -> None:
        """Demote rules that consistently fail."""
        for exp, info in list(self.experiments.items()):
            for rname, rinfo in list(info.get("rules", {}).items()):
                trials = rinfo.get("trials", 0)
                if trials < min_trials:
                    continue
                success = rinfo.get("success", 0) / max(1, trials)
                if success < min_success:
                    self.demote_rule(rname, by="auto", experiment=exp)

    def add_rule(self, rule: ReflexRule) -> None:
        rule.manager = self
        self.rules.append(rule)

    def execute_rule(
        self,
        name: str,
        *,
        agent: str | None = None,
        persona: str | None = None,
    ) -> bool:
        """Execute a rule by name and record a trial."""
        rule = next((r for r in self.rules if r.name == name), None)
        if not rule:
            raise ValueError(name)
        return rule.execute(agent=agent, persona=persona)

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
    def record_trial(
        self,
        rule: ReflexRule,
        success: bool,
        duration: float,
        *,
        experiment: str | None = None,
        agent: str | None = None,
        persona: str | None = None,
    ) -> None:
        """Record a single rule execution."""
        exp = experiment or rule.name
        data = self.experiments.setdefault(exp, {"rules": {}, "history": [], "status": "running"})
        rdata = data["rules"].setdefault(
            rule.name,
            {"trials": 0, "success": 0, "fail": 0, "durations": [], "agents": {}, "personas": {}},
        )
        rdata["trials"] += 1
        rdata["durations"].append(duration)
        if success:
            rdata["success"] += 1
        else:
            rdata["fail"] += 1
        if agent:
            rdata["agents"][agent] = rdata["agents"].get(agent, 0) + 1
        if persona:
            rdata["personas"][persona] = rdata["personas"].get(persona, 0) + 1
        entry = {
            "rule": rule.name,
            "success": success,
            "duration": duration,
            "agent": agent,
            "persona": persona,
        }
        data["history"].append(entry)
        with self.TRIAL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"experiment": exp, **entry}) + "\n")
        self.history.append({"action": "trial", **entry, "experiment": exp})
        self.save_experiments()
        rs.log_reflex_learn({"trial": entry, "experiment": exp})

        if not rule.preferred and rdata["success"] >= self.autopromote_trials:
            self.promote_rule(rule.name, by="system", experiment=exp)
            data["status"] = "promoted"
        if rule.preferred and rdata["fail"] >= self.autopromote_trials:
            self.demote_rule(rule.name, by="system", experiment=exp)
            data["status"] = "demoted"
        self.save_experiments()

    # ------------------------------------------------------------------
    def _record_result(self, exp: str, rule: ReflexRule, success: bool, duration: float) -> None:
        self.record_trial(rule, success, duration, experiment=exp)
        data = self.experiments.get(exp)
        if data and all(info.get("trials", 0) >= self.autopromote_trials for info in data["rules"].values()):
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
                success = rule.execute()
                results[rule.name] = "ok" if success else "fail"
            except Exception as e:  # pragma: no cover - defensive
                results[rule.name] = str(e)
                success = False
            duration = time.time() - start
            self._record_result(f"{rule_a.name}_vs_{rule_b.name}", rule, success, duration)
        rs.log_reflex_learn({"ab_test": [rule_a.name, rule_b.name], "results": results})
        return rule_a if results.get(rule_a.name) == "ok" else rule_b

    def promote_rule(
        self,
        name: str,
        *,
        by: str = "system",
        persona: Optional[str] = None,
        experiment: str | None = None,
        policy: Optional[str] = None,
        reviewer: Optional[str] = None,
        approvers: Optional[List[str]] = None,
    ) -> None:
        rule = next((r for r in self.rules if r.name == name), None)
        if not rule or rule.frozen:
            return
        kwargs = {"approvers": approvers} if approvers is not None else {}
        if not final_approval.request_approval(f"promote {name}", **kwargs):
            return
        prev = rule.status
        rule.status = "preferred"
        rule.preferred = True
        self.history.append({"action": "promote", "rule": name, "by": by, "prev": prev})
        rs.log_reflex_learn({"promotion": name, "by": by, "experiment": experiment})
        rs.log_event("reflex", "promotion", by, name)
        self._audit(
            "promote",
            name,
            by=by,
            persona=persona,
            experiment=experiment,
            policy=policy,
            reviewer=reviewer,
            tags=None,
            prev=prev,
            current="preferred",
        )
        self.save_experiments()

    def demote_rule(
        self,
        name: str,
        *,
        by: str = "system",
        persona: Optional[str] = None,
        experiment: str | None = None,
        policy: Optional[str] = None,
        reviewer: Optional[str] = None,
        approvers: Optional[List[str]] = None,
    ) -> None:
        rule = next((r for r in self.rules if r.name == name), None)
        if not rule or rule.frozen:
            return
        kwargs = {"approvers": approvers} if approvers is not None else {}
        if not final_approval.request_approval(f"demote {name}", **kwargs):
            return
        prev = rule.status
        rule.status = "inactive"
        rule.preferred = False
        self.history.append({"action": "demote", "rule": name, "by": by, "prev": prev})
        rs.log_reflex_learn({"demotion": name, "by": by, "experiment": experiment})
        rs.log_event("reflex", "demotion", by, name)
        self._audit(
            "demote",
            name,
            by=by,
            persona=persona,
            experiment=experiment,
            policy=policy,
            reviewer=reviewer,
            tags=None,
            prev=prev,
            current="inactive",
        )
        self.save_experiments()

    def revert_last(self) -> None:
        if not self.history:
            return
        last = self.history.pop()
        rule = next((r for r in self.rules if r.name == last.get("rule")), None)
        if rule:
            prev = last.get("prev", "candidate")
            current = rule.status
            rule.status = prev
            rule.preferred = rule.status == "preferred"
            rs.log_reflex_learn({"revert": rule.name, "by": "system"})
            rs.log_event("reflex", "revert", "system", rule.name)
            self._audit("revert", rule.name, by="system", prev=current, current=prev)
        self.save_experiments()

    def freeze_rule(self, name: str) -> None:
        rule = next((r for r in self.rules if r.name == name), None)
        if not rule:
            return
        rule.frozen = True
        self._audit("freeze", name, by="system")

    def unfreeze_rule(self, name: str) -> None:
        rule = next((r for r in self.rules if r.name == name), None)
        if not rule:
            return
        rule.frozen = False
        self._audit("unfreeze", name, by="system")

    def edit_rule(self, name: str, **params: Any) -> None:
        rule = next((r for r in self.rules if r.name == name), None)
        if not rule or rule.frozen:
            return
        before = {k: getattr(rule, k) for k in params.keys() if hasattr(rule, k)}
        for k, v in params.items():
            if hasattr(rule, k):
                setattr(rule, k, v)
        after = {k: getattr(rule, k) for k in before.keys()}
        self._audit("edit", name, by="system", prev=json.dumps(before), current=json.dumps(after))

    def revert_rule(self, name: str) -> None:
        """Revert a rule to its previous status based on audit log."""
        entries = list(reversed(self.get_audit(name)))
        for entry in entries:
            if entry.get("action") in {"promote", "demote"}:
                prev = entry.get("prev", "candidate")
                current = entry.get("current", "candidate")
                rule = next((r for r in self.rules if r.name == name), None)
                if rule:
                    rule.status = prev
                    rule.preferred = prev == "preferred"
                    self._audit(
                        "manual_revert",
                        name,
                        by="system",
                        prev=current,
                        current=prev,
                    )
                    self.save_experiments()
                break

    def get_history(self, experiment: str | None = None) -> List[Dict[str, Any]]:
        """Return trial history across experiments or for one experiment."""
        if experiment:
            return self.experiments.get(experiment, {}).get("history", [])
        hist: List[Dict[str, Any]] = []
        for info in self.experiments.values():
            hist.extend(info.get("history", []))
        return hist

    def get_audit(
        self,
        target: str | None = None,
        *,
        agent: Optional[str] = None,
        persona: Optional[str] = None,
        policy: Optional[str] = None,
        action: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return audit trail entries with optional filters."""
        if not self.AUDIT_LOG.exists():
            return []
        lines = self.AUDIT_LOG.read_text(encoding="utf-8").splitlines()
        out: List[Dict[str, Any]] = []
        for ln in lines:
            try:
                entry = json.loads(ln)
            except Exception:
                continue
            out.append(entry)
        if target:
            out = [e for e in out if e.get("rule") == target or e.get("experiment") == target]
        if agent:
            out = [e for e in out if e.get("by") == agent]
        if persona:
            out = [e for e in out if e.get("persona") == persona]
        if policy:
            out = [e for e in out if e.get("policy") == policy]
        if action:
            out = [e for e in out if e.get("action") == action]
        return out

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
        elif trig_type == "conditional":
            func = item.get("check_func")
            if func:
                mod, fname = func.split(":", 1)
                check = getattr(__import__(mod, fromlist=[fname]), fname)
            else:
                check = lambda: False
            trig = ConditionalTrigger(check, float(item.get("interval", 1.0)))
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
    set_default_manager(mgr)
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
