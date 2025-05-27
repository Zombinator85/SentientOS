import os
import json
import logging
import time
from flask import Flask, request, jsonify, Response
from memory_manager import write_mem
from utils import chunk_message
from emotions import empty_emotion_vector
from api import actuator

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

RELAY_SECRET = os.getenv("RELAY_SECRET", "test-secret")


@app.route("/relay", methods=["POST"])
def relay():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403

    data = request.get_json() or {}
    message = data.get("message", "")
    model = data.get("model", "default").strip().lower()
    emotion_vector = data.get("emotions") or empty_emotion_vector()

    reply = f"Echo: {message} ({model})"
    write_mem(
        f"[RELAY] → Model: {model} | Message: {message}\n{reply}",
        tags=["relay", model],
        source="relay",
        emotions=emotion_vector,
    )
    return jsonify({"reply_chunks": chunk_message(reply)})


@app.route("/act", methods=["POST"])
def act():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403

    payload = request.get_json() or {}
    explanation = payload.pop("why", None)
    user = request.headers.get("X-User", "relay")
    call_id = write_mem(
        f"[ACT REQUEST] {json.dumps(payload)}",
        tags=["act", "request"],
        source=user,
    )
    if payload.pop("async", False):
        action_id = actuator.start_async(payload, explanation=explanation, user=user)
        return jsonify({"status": "queued", "action_id": action_id, "request_log_id": call_id})

    result = actuator.act(payload, explanation=explanation, user=user)
    result["request_log_id"] = call_id
    return jsonify(result)


@app.route("/act_status", methods=["POST"])
def act_status():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    aid = (request.get_json() or {}).get("id", "")
    return jsonify(actuator.get_status(aid))


@app.route("/act_stream", methods=["POST"])
def act_stream():
    if request.headers.get("X-Relay-Secret") != RELAY_SECRET:
        return "Forbidden", 403
    aid = (request.get_json() or {}).get("id", "")

    def gen():
        last = None
        while True:
            status = actuator.get_status(aid)
            if status != last:
                yield f"data: {json.dumps(status)}\n\n"
                last = status
            if status.get("status") in {"finished", "failed", "unknown"}:
                break
            time.sleep(0.5)

    return Response(gen(), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(debug=True)
