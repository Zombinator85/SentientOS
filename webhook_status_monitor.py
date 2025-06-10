"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""  # plint: disable=banner-order
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

"""Periodic checker for Telegram webhook URLs."""
from logging_config import get_log_path
import datetime
import json
import os
import time
from pathlib import Path

try:
    import requests  # type: ignore  # HTTP client optional
except Exception:  # pragma: no cover - optional
    requests = None

WEBHOOKS = [u.strip() for u in os.getenv("TELEGRAM_WEBHOOKS", "").split(",") if u.strip()]
INTERVAL = int(os.getenv("WEBHOOK_CHECK_SEC", "60"))
LOG_FILE = get_log_path("webhook_status.jsonl")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN = os.getenv("TELEGRAM_ADMIN")


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


def _send_alert(url: str, status: int | str) -> None:
    if not (TOKEN and ADMIN and requests is not None):
        return
    msg = f"Webhook {url} down: {status}"
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": ADMIN, "text": msg},
            timeout=5,
        )
    except Exception:
        pass


def run_loop() -> None:  # pragma: no cover - runtime loop
    while True:
        for url in WEBHOOKS:
            status = _check(url)
            if status != 200:
                _log(url, status)
                _send_alert(url, status)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    run_loop()
