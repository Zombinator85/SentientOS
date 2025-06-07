from logging_config import get_log_path
import json
import time
from dataclasses import dataclass, field
import importlib
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import json
import uuid

try:
    from playsound import playsound  # type: ignore  # simple audio playback
except Exception:  # pragma: no cover - optional
    playsound = None

try:
    from pythonosc import udp_client  # type: ignore  # OSC client lacks stubs
except Exception:  # pragma: no cover - optional
    udp_client = None

import notification


@dataclass
class FeedbackRule:
    """Rule describing an emotion threshold and action."""

    emotion: str
    threshold: float
    action: str
    greater: bool = True
    cooldown: float = 1.0
    duration: float = 0.0
    custom_check: Optional[Callable[[float, Dict[str, float], Dict[str, Any]], bool]] = None
    name: str = ""


@dataclass
class FeedbackManager:
    """Check emotion vectors against rules and trigger actions."""

    rules: List[FeedbackRule] = field(default_factory=list)
    actions: Dict[str, Callable[[FeedbackRule, int, float], None]] = field(default_factory=dict)
    last_trigger: Dict[Tuple[int, str, str], float] = field(default_factory=dict)
    active_since: Dict[Tuple[int, str, str], float] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    log_path: Path = get_log_path("feedback_actions.jsonl", "FEEDBACK_LOG")
    user_log_path: Path = get_log_path("reflex_user_feedback.jsonl", "FEEDBACK_USER_LOG")
    tuning_log_path: Path = get_log_path("reflex_tuning.jsonl", "REFLEX_TUNING_LOG")
    learning: bool = False
    rule_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    tuning_history: List[Dict[str, Any]] = field(default_factory=list)

    def add_rule(self, rule: FeedbackRule) -> None:
        self.rules.append(rule)

    def register_action(self, name: str, func: Callable[[FeedbackRule, int, float], None]) -> None:
        self.actions[name] = func

    def load_rules(self, path: str) -> None:
        if not Path(path).exists():
            return
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for item in data:
            func = item.pop("check_func", None)
            rule = FeedbackRule(**item)
            if func:
                mod, func_name = func.split(":", 1)
                rule.custom_check = getattr(importlib.import_module(mod), func_name)
            self.add_rule(rule)

    def process(self, user_id: int, emotions: Dict[str, float], context: Optional[Dict[str, Any]] = None) -> None:
        ts = time.time()
        context = context or {}
        for rule in self.rules:
            value = emotions.get(rule.emotion, 0.0)
            cond = value > rule.threshold if rule.greater else value < rule.threshold
            if rule.custom_check and not rule.custom_check(value, emotions, context):
                cond = False
            key = (user_id, rule.emotion, rule.action)
            if cond:
                self.active_since.setdefault(key, ts)
                if rule.duration and ts - self.active_since[key] < rule.duration:
                    continue
                last = self.last_trigger.get(key, 0.0)
                if ts - last < rule.cooldown:
                    continue
                self.last_trigger[key] = ts
                action = self.actions.get(rule.action)
                if action:
                    action(rule, user_id, value)
                action_id = uuid.uuid4().hex
                entry = {
                    "id": action_id,
                    "time": ts,
                    "user": user_id,
                    "emotion": rule.emotion,
                    "value": value,
                    "action": rule.action,
                }
                self.history.append(entry)
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
                self.request_feedback(rule, action_id)
                self.active_since.pop(key, None)
            else:
                self.active_since.pop(key, None)

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.history[-limit:]

    # ------------------------------------------------------------------
    def log_user_feedback(self, action_id: str, rule: FeedbackRule, rating: int, comment: str = "") -> None:
        entry = {
            "time": time.time(),
            "action_id": action_id,
            "rule": rule.name or rule.action,
            "rating": rating,
            "comment": comment,
        }
        self.user_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.user_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        stats = self.rule_stats.setdefault(rule.name or rule.action, {"hits": 0, "positive": 0})
        stats["hits"] += 1
        if rating > 0:
            stats["positive"] += 1
        if self.learning:
            self._maybe_tune(rule, stats)

    def request_feedback(self, rule: FeedbackRule, action_id: str) -> None:
        if os.getenv("FEEDBACK_NO_PROMPT"):
            return
        try:
            resp = input(f"Did action '{rule.action}' help? (y/n or comment) ").strip()
        except Exception:
            return
        if not resp:
            return
        rating = 1 if resp.lower().startswith("y") else 0
        comment = "" if resp.lower() in {"y", "n"} else resp
        self.log_user_feedback(action_id, rule, rating, comment)

    def _maybe_tune(self, rule: FeedbackRule, stats: Dict[str, int]) -> None:
        if stats["hits"] < 5:
            return
        rate = stats["positive"] / max(1, stats["hits"])
        before = {"threshold": rule.threshold, "cooldown": rule.cooldown}
        rationale = ""
        tuned = False
        if rate > 0.7 and rule.threshold > 0.1:
            rule.threshold = max(0.0, rule.threshold - 0.05)
            rationale = f"success rate {rate:.2f} - lowering threshold"
            tuned = True
        elif rate < 0.3 and rule.threshold < 1.0:
            rule.threshold = min(1.0, rule.threshold + 0.05)
            rule.cooldown += 1
            rationale = f"low success {rate:.2f} - raising threshold"
            tuned = True
        if tuned:
            after = {"threshold": rule.threshold, "cooldown": rule.cooldown}
            log = {
                "time": time.time(),
                "rule": rule.name or rule.action,
                "before": before,
                "after": after,
                "rationale": rationale,
            }
            self.tuning_history.append(log)
            self.tuning_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.tuning_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log) + "\n")
        stats["hits"] = 0
        stats["positive"] = 0


# ----- Built-in actions -----

def print_action(rule: FeedbackRule, user_id: int, value: float) -> None:
    print(f"[FEEDBACK] user {user_id} {rule.emotion}={value:.2f} -> {rule.action}")


def sound_action_factory(path: str) -> Callable[[FeedbackRule, int, float], None]:
    def _action(rule: FeedbackRule, user_id: int, value: float) -> None:
        if playsound:
            try:
                playsound(path, block=False)
            except Exception:  # pragma: no cover - device failure
                pass
    return _action


def osc_action_factory(host: str, port: int, address: str = "/emotion") -> Callable[[FeedbackRule, int, float], None]:
    def _action(rule: FeedbackRule, user_id: int, value: float) -> None:
        if udp_client:
            try:
                client = udp_client.SimpleUDPClient(host, port)
                client.send_message(address, [user_id, rule.emotion, value])
            except Exception:  # pragma: no cover - network failure
                pass
    return _action


def positive_cue(rule: FeedbackRule, user_id: int, value: float) -> None:
    """Simple placeholder positive feedback."""
    print(f"[CUE] user {user_id} confidence {value:.2f} -> positive cue")


def calming_routine(rule: FeedbackRule, user_id: int, value: float) -> None:
    """Placeholder calming action triggered on stress."""
    notification.send("calming.start", {"user": user_id, "emotion": rule.emotion, "value": value})
