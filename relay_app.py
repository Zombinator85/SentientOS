import os
import json
import logging
from flask import Flask, request, jsonify
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

    intent = request.get_json() or {}
    try:
        result = actuator.dispatch(intent)
    except Exception as e:
        result = {"error": str(e)}

    write_mem(
        f"[ACT] Intent: {json.dumps(intent)}\nResult: {json.dumps(result)}",
        tags=["act"],
        source="relay",
    )

    try:
        with app.test_request_context(
            "/relay",
            method="POST",
            json={
                "message": f"Why was action {intent} chosen?",
                "model": intent.get("model", "default"),
            },
            headers={"X-Relay-Secret": RELAY_SECRET},
        ):
            exp_resp = relay()
            explanation = exp_resp.get_json()["reply_chunks"][0]
            write_mem(
                f"[ACT EXPLAIN] {explanation}",
                tags=["act", "explain"],
                source="relay",
            )
    except Exception as e:  # pragma: no cover - best-effort
        write_mem(
            f"[ACT EXPLAIN ERROR] {e}",
            tags=["act", "explain"],
            source="relay",
        )

    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)
