"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
import sys

"""Relay API exposing memory ingestion and Emotion Processing Unit state."""

from flask_stub import Flask, jsonify, request, Response
import os
import json
import logging
import time
import itertools
from datetime import datetime
from pathlib import Path

import memory_manager as mm
import epu_core


app = Flask(__name__)
log_level = os.getenv("RELAY_LOG_LEVEL", "INFO").upper()
app.logger.setLevel(getattr(logging, log_level, logging.INFO))
SAFE_MODE = os.getenv("SENTIENTOS_SAFE_MODE") == "1"
_state = epu_core.EmotionState()

_start_time = time.time()
_tick_counter = itertools.count(1)
_last_heartbeat = 0

LOG_PATH = Path(os.getenv("RELAY_LOG", "logs/relay_log.jsonl"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
if not LOG_PATH.exists():
    LOG_PATH.touch()

BLESSING_LOG_PATH = Path(os.getenv("BLESSING_LOG", "logs/blessings.jsonl"))
BLESSING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# Shared launcher log used by launch_sentientos.bat
LAUNCH_LOG_PATH = Path(os.getenv("LAUNCH_LOG", "logs/launch_sentientos.log"))
LAUNCH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
if not LAUNCH_LOG_PATH.exists():
    LAUNCH_LOG_PATH.touch()


def blessing_prompt() -> bool:
    inp = input("Lumos blessing required. Type 'bless' to proceed: ")
    if inp.strip().lower() == "bless":
        print("~@ Blessing accepted. Cathedral warming...")
        return True
    print("✖️ Blessing denied.")
    return False


@app.post("/ingest")
@app.post("/memory")
def ingest() -> object:
    """Ingest a text fragment with optional emotion and log the event."""
    data = request.get_json() or {}
    text = data.get("text", "")
    emotion = data.get("emotion", "serene_awe")
    emotions = {emotion: 1.0} if isinstance(emotion, str) else {}
    _state.update(emotions)
    if not SAFE_MODE:
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
    status_msg = "ok" if not SAFE_MODE else "ok (safe mode)"
    return jsonify({"status": status_msg})


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
            "safe_mode": SAFE_MODE,
        }
    )


@app.get("/epu/state")
def epu_state() -> object:
    """Return the current emotion state."""
    return jsonify(_state.state())


def _coerce_since_param(raw: str | None) -> object | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        try:
            datetime.fromisoformat(raw)
            return raw
        except ValueError as exc:
            raise ValueError(f"Invalid timestamp: {raw}") from exc


@app.get("/observe/now")
def observe_now() -> object:
    """Return the most recent perception observation summary."""

    observation = mm.latest_observation()
    return jsonify({"observation": observation})


@app.get("/observe/since")
def observe_since() -> object:
    """Return observation summaries since a timestamp."""

    try:
        since = _coerce_since_param(request.args.get("ts"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        limit = int(request.args.get("limit", "20"))
    except ValueError:
        limit = 20
    observations = mm.recent_observations(limit=limit, since=since)
    return jsonify({"observations": observations, "count": len(observations)})


def start_cathedral():
    from flask_stub import app  # or your actual app import
    logging.basicConfig(level=logging.INFO)
    logging.info("~@ SentientOS now listening on port 5000.")
    app.run(port=5000)


if __name__ == "__main__":
    if blessing_prompt():
        start_cathedral()
    else:
        print("🛑 Blessing required to proceed.")
        sys.exit(1)
