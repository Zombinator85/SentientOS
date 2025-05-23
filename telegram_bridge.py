import logging
import os
import requests
import threading
import time
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from utils import chunk_message
from memory_manager import write_mem

load_dotenv()
logging.basicConfig(level=logging.INFO)

class TelegramBridge:
    def __init__(self, model_slug: str, bot_token: str, port: int,
                 relay_url: str | None = None,
                 relay_secret: str | None = None,
                 tg_secret: str | None = None,
                 chunk: int = 4096):
        self.model_slug = model_slug.strip().lower()
        self.bot_token = bot_token
        self.port = port
        self.relay_url = relay_url or os.getenv("RELAY_URL")
        self.relay_secret = relay_secret or os.getenv("RELAY_SECRET")
        self.tg_secret = tg_secret or os.getenv("TG_SECRET")
        self.chunk = chunk
        self.send_api = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        self.app = Flask(__name__)
        self._register_routes()

    # --- Helper functions ---
    def _send_typing(self, chat_id: int) -> None:
        try:
            requests.post(
                self.send_api.replace("/sendMessage", "/sendChatAction"),
                json={"chat_id": chat_id, "action": "typing"},
                timeout=8,
            )
        except Exception:
            pass

    def _send_message(self, chat_id: int, text: str) -> None:
        for chunk in chunk_message(text, self.chunk):
            time.sleep(1.2)
            try:
                res = requests.post(
                    self.send_api,
                    json={"chat_id": chat_id, "text": chunk},
                    timeout=20,
                )
                logging.info("[SEND] %s -> %s", self.model_slug, res.status_code)
            except Exception:
                logging.exception("[ERROR] Telegram send failed")

    def _handle_async(self, chat_id: int, txt: str) -> None:
        logging.info("[THREAD] %s handling -> %s", self.model_slug, txt[:60])
        write_mem(txt, tags=["telegram", self.model_slug],
                  source=f"telegram:{self.model_slug}")
        self._send_typing(chat_id)
        try:
            res = requests.post(
                self.relay_url,
                json={"message": txt.strip(), "model": self.model_slug},
                headers={"X-Relay-Secret": self.relay_secret},
                timeout=90,
            )
            reply_chunks = res.json().get("reply_chunks", [])
            if not reply_chunks:
                reply_chunks = [f"[{self.model_slug} Error] No reply received."]
            for chunk in reply_chunks:
                write_mem(chunk, tags=["telegram", self.model_slug],
                          source=f"telegram:{self.model_slug}")
                self._send_message(chat_id, chunk)
        except Exception as e:
            logging.error("[RELAY ERROR] %s", e)

    def _bridge(self):
        m = (request.get_json(silent=True) or {}).get("message", {})
        cid = m.get("chat", {}).get("id")
        txt = m.get("text", "")
        if not cid or not txt:
            return "no message", 400
        threading.Thread(target=self._handle_async, args=(cid, txt)).start()
        return jsonify({"status": "processing"}), 200

    def _register_routes(self):
        @self.app.route("/webhook", methods=["POST"])
        def webhook():
            if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != self.tg_secret:
                return "forbidden", 403
            return self._bridge()

    def run(self):
        self.app.run("0.0.0.0", self.port, threaded=True)
