from logging_config import get_log_path
import json
from pathlib import Path
from flask_stub import Flask, request

app = Flask(__name__)
LOG_DIR = get_log_path("webhooks")
LOG_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/webhook/<event>", methods=["POST"])
def receive(event: str):
    payload = request.get_json(force=True, silent=True) or {}
    log_path = LOG_DIR / f"{event}.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")
    return {"status": "ok"}


if __name__ == "__main__":  # pragma: no cover - manual server
    app.run(port=5080)
