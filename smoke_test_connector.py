from subprocess import CalledProcessError, check_call
import sys
import time
import json
from pathlib import Path
import os
from logging_config import get_log_path
import openai_connector

print("Running connector smoke tests...")


def run_once() -> None:
    check_call([sys.executable, "privilege_lint_cli.py"])
    check_call([sys.executable, "-m", "pytest", "-q", "tests/test_openai_connector.py"])
    check_call([sys.executable, "check_connector_health.py"])
    client = openai_connector.app.test_client()
    assert json.loads(openai_connector.healthz()) == {"status": "ok"}
    metrics = openai_connector.metrics().data
    if isinstance(metrics, bytes):
        metrics = metrics.decode()
    assert "events_total" in metrics


for attempt in range(3):
    try:
        run_once()
        break
    except CalledProcessError:
        if attempt == 2:
            raise
        wait = 2 ** attempt
        print(f"Retrying in {wait}s...")
        time.sleep(wait)

log_path = get_log_path("openai_connector.jsonl", "OPENAI_CONNECTOR_LOG")
if log_path.exists():
    with log_path.open() as f:
        lines = [json.loads(x) for x in f if x.strip()]
    if lines:
        print("last event", lines[-1].get("event"))
    rotated = log_path.with_suffix(log_path.suffix + ".1").exists()
    print("log rotation", rotated)

print("done")
