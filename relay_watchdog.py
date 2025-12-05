"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
"""Watchdog for sentient_api daemon health."""

import datetime
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List

from logging_config import get_log_path
import json

try:
    import requests
except Exception:  # pragma: no cover - optional
    requests = None

CHECK_INTERVAL = float(os.getenv("RELAY_CHECK_SEC", "5"))
CHECK_URLS: List[str] = [u.strip() for u in os.getenv("RELAY_URLS", "http://localhost:3928/status").split(",") if u.strip()]
RESTART_CMD = os.getenv("RELAY_RESTART_CMD", "")
LOG_FILE = get_log_path("daemon_watchdog.jsonl")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

_state: Dict[str, bool] = {}


def _log(event: str, target: str, detail: str = "") -> None:
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "event": event,
        "target": target,
        "detail": detail,
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


import json


def _check(url: str) -> bool:
    if requests is None:
        return True
    try:
        resp = requests.get(url, timeout=2)
        return resp.status_code == 200
    except Exception as e:  # pragma: no cover - network errors
        _log("error", url, str(e))
        return False


def _restart() -> bool:
    if not RESTART_CMD:
        return False
    try:
        subprocess.run(RESTART_CMD.split(), check=True)
        _log("restart", RESTART_CMD)
        return True
    except Exception as e:  # pragma: no cover - restart issues
        _log("restart_failed", RESTART_CMD, str(e))
        return False


def run_loop() -> None:  # pragma: no cover - real-time loop
    print(f"[WATCHDOG] Monitoring {', '.join(CHECK_URLS)}")
    while True:
        for url in CHECK_URLS:
            ok = _check(url)
            prev = _state.get(url, True)
            _state[url] = ok
            if ok:
                if not prev:
                    _log("recovered", url)
                continue
            _log("down", url)
            if _restart():
                _state[url] = True
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":  # pragma: no cover - manual
    run_loop()
