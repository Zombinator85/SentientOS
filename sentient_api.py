"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Relay API exposing memory ingestion and Emotion Processing Unit state."""

from flask_stub import Flask, jsonify, request, Response
import os
import json
import time
import itertools
from datetime import datetime
from pathlib import Path

import memory_manager as mm
import epu_core


app = Flask(__name__)
_state = epu_core.EmotionState()

_start_time = time.time()
_tick_counter = itertools.count(1)
_last_heartbeat = 0

LOG_PATH = Path(os.getenv("RELAY_LOG", "logs/relay_log.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


@app.post("/ingest")
@app.post("/memory")
def ingest() -> object:
    """Ingest a text fragment with optional emotion and log the event."""
    data = request.get_json() or {}
    text = data.get("text", "")
    emotion = data.get("emotion", "serene_awe")
    emotions = {emotion: 1.0} if isinstance(emotion, str) else {}
    _state.update(emotions)
    mm.append_memory(text, emotions=emotions)

    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "text": text,
        "emotion": emotion,
        "ritual": "manual_ingest",
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    global _last_heartbeat
    _last_heartbeat = next(_tick_counter)
    return jsonify({"status": "ok"})


@app.get("/sse")
def sse() -> Response:
    """Stream heartbeat ticks as server-sent events."""

    def gen():
        global _last_heartbeat
        while True:
            _last_heartbeat = next(_tick_counter)
            payload = json.dumps({"tick": _last_heartbeat})
            yield f"data: {payload}\n\n"
            time.sleep(1)

    return Response(gen(), mimetype="text/event-stream")


@app.get("/status")
def status() -> object:
    """Return uptime, last heartbeat, log size and active endpoints."""
    uptime_seconds = int(time.time() - _start_time)
    days, rem = divmod(uptime_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    uptime = f"{days}d {hours:02}:{minutes:02}:{seconds:02}"
    log_size = LOG_PATH.stat().st_size if LOG_PATH.exists() else 0
    return jsonify(
        {
            "uptime": uptime,
            "last_heartbeat": f"Tick {_last_heartbeat}",
            "log_size_bytes": log_size,
            "active_endpoints": ["/sse", "/ingest", "/status"],
        }
    )


@app.get("/epu/state")
def epu_state() -> object:
    """Return the current emotion state."""
    return jsonify(_state.state())


if __name__ == "__main__":  # pragma: no cover - manual
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
