"""Custom reflex actions for bridge monitoring and daily digest."""
from __future__ import annotations
from logging_config import get_log_path
import json
import datetime
from pathlib import Path
from api import actuator
import notification
import daily_digest


def bridge_restart_check() -> None:
    """Check recent restart events and escalate if too frequent."""
    log = get_log_path("bridge_watchdog.jsonl")
    now = datetime.datetime.utcnow()
    cutoff = now - datetime.timedelta(minutes=10)
    count = 0
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                data = json.loads(line)
            except Exception:
                continue
            if data.get("event") != "restart":
                continue
            try:
                ts = datetime.datetime.fromisoformat(data.get("timestamp", ""))
            except Exception:
                continue
            if ts >= cutoff:
                count += 1
    metrics = {"timestamp": now.isoformat(), "recent_restarts": count}
    metric_path = get_log_path("bridge_metrics.json")
    metric_path.parent.mkdir(parents=True, exist_ok=True)
    metric_path.write_text(json.dumps(metrics))
    notification.send("bridge.restart", metrics)
    if count > 3:
        actuator.dispatch({"type": "escalate", "goal": "bridge", "text": "failover"})
        notification.send("bridge.failover", metrics)


def daily_digest_action() -> None:
    """Generate a daily log digest and notify listeners."""
    summary = daily_digest.run_digest()
    notification.send("daily.digest", summary)
