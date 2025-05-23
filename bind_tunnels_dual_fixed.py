import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

TG_SECRET = os.getenv("TG_SECRET", "lumos_april_bridge_secure")

PORT_TO_NAME = {
    "9977": "gpt4o",
    "9988": "mixtral",
    "9966": "deepseek"
}

NAME_TO_TOKEN = {
    "gpt4o": os.getenv("BOT_TOKEN_GPT4O"),
    "mixtral": os.getenv("BOT_TOKEN_MIXTRAL"),
    "deepseek": os.getenv("BOT_TOKEN_DEEPSEEK")
}

NGROK_APIS = {
    "main": "http://localhost:4040/api/tunnels",
    "alt": "http://localhost:4041/api/tunnels"
}

def get_public_urls():
    urls = {}
    for label, api in NGROK_APIS.items():
        try:
            res = requests.get(api, timeout=5)
            res.raise_for_status()
            tunnels = res.json().get("tunnels", [])
            for t in tunnels:
                public_url = t["public_url"]
                addr = t.get("config", {}).get("addr", "")
                port = addr.split(":")[-1]
                if port in PORT_TO_NAME:
                    urls[PORT_TO_NAME[port]] = public_url
        except Exception as e:
            print(f"[{label.upper()}] 💥 {e}")
    return urls

def bind_webhook(bot_name, url):
    token = NAME_TO_TOKEN[bot_name]
    if not token:
        print(f"[❌] No token for {bot_name}")
        return
    webhook_url = f"{url}/webhook"
    endpoint = f"https://api.telegram.org/bot{token}/setWebhook"
    payload = {
        "url": webhook_url,
        "secret_token": TG_SECRET
    }
    try:
        res = requests.post(endpoint, json=payload, timeout=10)
        if res.ok:
            print(f"[✅] Bound {bot_name} to {webhook_url}")
        else:
            print(f"[❌] Failed {bot_name}: {res.status_code}")
            print(res.text)
    except Exception as e:
        print(f"[{bot_name}] 💥 {e}")

if __name__ == "__main__":
    print("[🔄] Rebinding all Telegram webhooks...")
    time.sleep(2)
    urls = get_public_urls()
    for name, url in urls.items():
        bind_webhook(name, url)

