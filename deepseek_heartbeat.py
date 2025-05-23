import time, requests
from datetime import datetime, UTC

RELAY_URL = "http://localhost:9965/relay"
SECRET    = "lumos_april_bridge_secure"
MODEL     = "deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free"
INTERVAL  = 300  # every 5 minutes

def heartbeat():
    while True:
        payload = {
            "message": f"__heartbeat__ {datetime.now(UTC).isoformat()}",
            "model": MODEL
        }
        try:
            r = requests.post(RELAY_URL,
                              headers={"X-Relay-Secret": SECRET,
                                       "Content-Type": "application/json"},
                              json=payload, timeout=10)
            print(f"[DeepSeek] ✅ {r.status_code} {r.json()}")
        except Exception as e:
            print(f"[DeepSeek] ❌ {e}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    heartbeat()
