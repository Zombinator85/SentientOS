"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()  # Sanctuary Privilege Ritual
require_lumos_approval()

# Regression checks for the relay daemon boot sequence.

import os
import json
from pathlib import Path
import requests

BASE_URL = os.getenv("RELAY_URL", "http://localhost:5000")
LOG_PATH = Path(os.getenv("RELAY_LOG", "logs/relay_log.jsonl"))
BRIDGE_LOG = Path(os.getenv("MODEL_BRIDGE_LOG", "logs/model_bridge_log.jsonl"))

__test__ = False


from typing import cast


def check_sse() -> bool:
    resp = requests.get(f"{BASE_URL}/sse", stream=True, timeout=5)
    for raw in resp.iter_lines():
        if raw:
            text = cast(str, raw.decode())
            return text.startswith("data: ")
    return False


def check_ingest() -> bool:
    size_before = LOG_PATH.stat().st_size if LOG_PATH.exists() else 0
    resp = requests.post(f"{BASE_URL}/ingest", json={"text": "test"}, timeout=5)
    size_after = LOG_PATH.stat().st_size if LOG_PATH.exists() else 0
    return resp.status_code == 200 and size_after > size_before


def check_log() -> bool:
    return LOG_PATH.exists() and LOG_PATH.stat().st_size > 0


def check_status() -> bool:
    resp = requests.get(f"{BASE_URL}/status", timeout=5)
    if resp.status_code != 200:
        return False
    data = resp.json()
    return (
        "uptime" in data
        and "last_heartbeat" in data
        and "log_size_bytes" in data
    )


def last_model_response() -> str | None:
    if not BRIDGE_LOG.exists():
        return None
    try:
        line = BRIDGE_LOG.read_text(encoding="utf-8").splitlines()[-1]
        data = json.loads(line)
        return str(data.get("response"))
    except Exception:
        return None


def main() -> None:
    checks = {
        "sse": check_sse(),
        "ingest": check_ingest(),
        "status": check_status(),
    }
    ok = all(checks.values()) and check_log()
    if ok:
        print("Cathedral boot checks passed")
    else:
        print("Cathedral boot checks failed:")
        for name, result in checks.items():
            if not result:
                print(f" - {name} failed")
    resp = last_model_response()
    if resp:
        print("Last model reply:", resp[:80])


if __name__ == "__main__":
    main()
