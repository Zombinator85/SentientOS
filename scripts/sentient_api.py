from flask import Flask, request, jsonify, Response
import time, json
from datetime import datetime

app = Flask(__name__)

@app.route("/sse")
def sse():
    def event_stream():
        counter = 0
        while True:
            counter += 1
            data = {
                "event_type": "heartbeat",
                "content": f"Tick {counter}",
                "timestamp": datetime.utcnow().isoformat()
            }
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(5)
    return Response(event_stream(), mimetype="text/event-stream")

@app.route("/ingest", methods=["POST"])
def ingest():
    payload = request.json
    print(f"📥 Received payload: {json.dumps(payload, indent=2)}")
    return jsonify({"status": "received", "received_at": datetime.utcnow().isoformat()})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
