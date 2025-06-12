"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import time
import requests
from datetime import datetime, UTC
from emotions import empty_emotion_vector

RELAY_URL = "http://localhost:5000/relay"
SECRET = "lumos_april_bridge_secure"
MODEL = "openai/gpt-4o"
INTERVAL = 300  # every 5 minutes


def heartbeat():
    """Send a heartbeat message at regular intervals."""
    while True:
        payload = {
            "message": f"__heartbeat__ {datetime.now(UTC).isoformat()}",
            "model": MODEL,
            "emotions": empty_emotion_vector(),
        }
        try:
            r = requests.post(
                RELAY_URL,
                headers={"X-Relay-Secret": SECRET, "Content-Type": "application/json"},
                json=payload,
                timeout=10,
            )
            print(f"[GPT-4o] ✅ {r.status_code} {r.json()}")
        except Exception as e:
            print(f"[GPT-4o] ❌ {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    heartbeat()
