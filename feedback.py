import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

try:
    from playsound import playsound  # type: ignore
except Exception:  # pragma: no cover - optional
    playsound = None

try:
    from pythonosc import udp_client  # type: ignore
except Exception:  # pragma: no cover - optional
    udp_client = None


@dataclass
class FeedbackRule:
    """Rule describing an emotion threshold and action."""

    emotion: str
    threshold: float
    action: str
    greater: bool = True
    cooldown: float = 1.0


@dataclass
class FeedbackManager:
    """Check emotion vectors against rules and trigger actions."""

    rules: List[FeedbackRule] = field(default_factory=list)
    actions: Dict[str, Callable[[FeedbackRule, int, float], None]] = field(default_factory=dict)
    last_trigger: Dict[Tuple[int, str], float] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def add_rule(self, rule: FeedbackRule) -> None:
        self.rules.append(rule)

    def register_action(self, name: str, func: Callable[[FeedbackRule, int, float], None]) -> None:
        self.actions[name] = func

    def load_rules(self, path: str) -> None:
        if not Path(path).exists():
            return
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for item in data:
            self.add_rule(FeedbackRule(**item))

    def process(self, user_id: int, emotions: Dict[str, float]) -> None:
        ts = time.time()
        for rule in self.rules:
            value = emotions.get(rule.emotion, 0.0)
            cond = value > rule.threshold if rule.greater else value < rule.threshold
            last = self.last_trigger.get((user_id, rule.emotion), 0.0)
            if cond and ts - last >= rule.cooldown:
                self.last_trigger[(user_id, rule.emotion)] = ts
                action = self.actions.get(rule.action)
                if action:
                    action(rule, user_id, value)
                self.history.append(
                    {
                        "time": ts,
                        "user": user_id,
                        "emotion": rule.emotion,
                        "value": value,
                        "action": rule.action,
                    }
                )

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
