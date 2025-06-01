"""Periodic checker for Telegram webhook URLs."""
import datetime
import json
import os
import time
from pathlib import Path

try:
    import requests
except Exception:  # pragma: no cover - optional
    requests = None

WEBHOOKS = [u.strip() for u in os.getenv("TELEGRAM_WEBHOOKS", "").split(",") if u.strip()]
INTERVAL = int(os.getenv("WEBHOOK_CHECK_SEC", "60"))
LOG_FILE = Path("logs/webhook_status.jsonl")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _log(url: str, status: int | str) -> None:
    entry = {"timestamp": datetime.datetime.utcnow().isoformat(), "url": url, "status": status}
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _check(url: str) -> int | str:
    if requests is None:
        return 200
    try:
        r = requests.get(url, timeout=5)
        return r.status_code
    except Exception as e:  # pragma: no cover - network errors
        return str(e)


def run_loop() -> None:  # pragma: no cover - runtime loop
    while True:
        for url in WEBHOOKS:
            status = _check(url)
            if status != 200:
                _log(url, status)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    run_loop()
