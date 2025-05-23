import os
import time
import requests
from datetime import datetime, UTC

RELAY_URL = os.getenv("RELAY_URL", "http://localhost:5000/relay")
RELAY_SECRET = os.getenv("RELAY_SECRET", "lumos_april_bridge_secure")
MODEL = os.getenv("GPT4_MODEL", "openai/gpt-4o")
INTERVAL = 300  # every 5 minutes


def heartbeat():
    """Send a heartbeat message at regular intervals."""
    while True:
        payload = {
            "message": f"__heartbeat__ {datetime.now(UTC).isoformat()}",
            "model": MODEL,
        }
        try:
            r = requests.post(
                RELAY_URL,
                headers={"X-Relay-Secret": RELAY_SECRET, "Content-Type": "application/json"},
                json=payload,
                timeout=10,
            )
            print(f"[GPT-4o] ✅ {r.status_code} {r.json()}")
        except Exception as e:
            print(f"[GPT-4o] ❌ {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    heartbeat()
