import os
import logging
from flask import Flask, request, jsonify
from memory_manager import write_mem
from utils import chunk_message

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

    reply = f"Echo: {message} ({model})"
    write_mem(f"[RELAY] → Model: {model} | Message: {message}\n{reply}", tags=["relay", model], source="relay")
    return jsonify({"reply_chunks": chunk_message(reply)})


if __name__ == "__main__":
    app.run(debug=True)
