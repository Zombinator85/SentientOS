"""Core API exposing EPU state and memory ingest."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from flask import Flask, jsonify, request
import os

import memory_manager as mm
import epu_core


app = Flask(__name__)
_state = epu_core.EmotionState()


@app.post("/memory")
def add_memory() -> object:
    data = request.get_json() or {}
    text = data.get("text", "")
    emotion = data.get("emotion")
    emotions = {emotion: 1.0} if isinstance(emotion, str) else {}
    _state.update(emotions)
    mm.append_memory(text, emotions=emotions)
    return jsonify({"status": "ok"})


@app.get("/epu/state")
def epu_state() -> object:
    return jsonify(_state.state())


if __name__ == "__main__":  # pragma: no cover - manual
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
