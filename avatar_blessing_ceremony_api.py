from __future__ import annotations
from logging_config import get_log_path

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
"""Avatar Blessing Ceremony API."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from flask import Flask, jsonify, request

LOG_PATH = get_log_path("avatar_blessing_ceremony.jsonl", "AVATAR_BLESSING_CEREMONY_LOG")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)


def log_blessing(avatar: str, blessing: str, celebrant: str) -> Dict[str, str]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "blessing": blessing,
        "celebrant": celebrant,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def list_blessings() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


@app.post("/blessings")
def api_log_blessing():
    data = request.json or {}
    avatar = data.get("avatar", "")
    blessing = data.get("blessing", "")
    celebrant = data.get("celebrant", "")
    entry = log_blessing(avatar, blessing, celebrant)
    return jsonify(entry)


@app.get("/blessings")
def api_list_blessings():
    return jsonify(list_blessings())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
