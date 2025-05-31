import json
import time
from dataclasses import dataclass, field
import importlib
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from playsound import playsound  # type: ignore
except Exception:  # pragma: no cover - optional
    playsound = None

try:
    from pythonosc import udp_client  # type: ignore
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


@dataclass
class FeedbackManager:
    """Check emotion vectors against rules and trigger actions."""

    rules: List[FeedbackRule] = field(default_factory=list)
    actions: Dict[str, Callable[[FeedbackRule, int, float], None]] = field(default_factory=dict)
    last_trigger: Dict[Tuple[int, str, str], float] = field(default_factory=dict)
    active_since: Dict[Tuple[int, str, str], float] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    log_path: Path = Path(os.getenv("FEEDBACK_LOG", "logs/feedback_actions.jsonl"))

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
                entry = {
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
                self.active_since.pop(key, None)
            else:
                self.active_since.pop(key, None)

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.history[-limit:]


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
