from logging_config import get_log_path
import json
from pathlib import Path
from flask_stub import Flask, request

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
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
    require_admin_banner()
    app.run(port=5080)
