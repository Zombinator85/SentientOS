import os
import requests
import logging
import time
import threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from utils import chunk_message
from memory_manager import write_mem

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
RELAY_URL = os.getenv("RELAY_URL")
RELAY_SECRET = os.getenv("RELAY_SECRET")
MODEL_SLUG = os.getenv("MODEL_SLUG", "openai/gpt-4o").strip().lower()
TG_SECRET = os.getenv("TG_SECRET")
PORT = int(os.getenv("PORT", "9977"))
CHUNK = 4096

SEND_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)


def send_typing(chat_id: int) -> None:
    try:
        requests.post(
            SEND_API.replace("/sendMessage", "/sendChatAction"),
            json={"chat_id": chat_id, "action": "typing"},
            timeout=8,
        )
    except Exception:
        pass


def send_message(chat_id: int, text: str) -> None:
    for chunk in chunk_message(text, CHUNK):
        time.sleep(1.2)
        try:
            requests.post(SEND_API, json={"chat_id": chat_id, "text": chunk}, timeout=20)
        except Exception:
            logging.exception("[ERROR] Telegram send failed")


def handle_message_async(chat_id: int, txt: str) -> None:
    logging.info(f"[THREAD] handling → {txt[:60]}")
    write_mem(txt, tags=["telegram"], source=f"telegram:{MODEL_SLUG}")
    send_typing(chat_id)
    try:
        res = requests.post(
            RELAY_URL,
            json={"message": txt.strip(), "model": MODEL_SLUG},
            headers={"X-Relay-Secret": RELAY_SECRET},
            timeout=60,
        )
        reply_chunks = res.json().get("reply_chunks", [])
        for chunk in reply_chunks:
            write_mem(chunk, tags=["telegram"], source=f"telegram:{MODEL_SLUG}")
            send_message(chat_id, chunk)
    except Exception as e:
        logging.error(f"[RELAY ERROR] {e}")


def bridge():
    data = request.get_json(silent=True) or {}
    m = data.get("message", {})
    cid = m.get("chat", {}).get("id")
    txt = m.get("text", "")
    if not cid or not txt:
        return "no message", 400
    threading.Thread(target=handle_message_async, args=(cid, txt)).start()
    return jsonify({"status": "processing"}), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != TG_SECRET:
        return "forbidden", 403
    return bridge()


if __name__ == "__main__":
    app.run("0.0.0.0", PORT, threaded=True)
