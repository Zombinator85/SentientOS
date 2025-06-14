from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Regression checks for the relay daemon boot sequence."""

import os
import json
from pathlib import Path
import requests

BASE_URL = os.getenv("RELAY_URL", "http://localhost:5000")
LOG_PATH = Path(os.getenv("RELAY_LOG", "logs/relay_log.jsonl"))

__test__ = False


def check_sse() -> bool:
    resp = requests.get(f"{BASE_URL}/sse", stream=True, timeout=5)
    for line in resp.iter_lines():
        if line:
            return line.startswith(b"data: ")
    return False


def check_ingest() -> bool:
    resp = requests.post(f"{BASE_URL}/ingest", json={"text": "test"}, timeout=5)
    return resp.status_code == 200


def check_log() -> bool:
    return LOG_PATH.exists() and LOG_PATH.stat().st_size > 0


def check_status() -> bool:
    resp = requests.get(f"{BASE_URL}/status", timeout=5)
    if resp.status_code != 200:
        return False
    data = resp.json()
    return "uptime" in data and data.get("last_heartbeat", "").startswith("Tick")


def main() -> None:
    ok = check_ingest() and check_log() and check_status() and check_sse()
    if ok:
        print("Cathedral boot checks passed")
    else:
        print("Cathedral boot checks failed")


if __name__ == "__main__":
    main()
