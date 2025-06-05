"""Lightweight Flask dashboard for emotion vector via UDP."""
import json
import socket
import threading
import time
from typing import List
from flask_stub import Flask, jsonify, send_file
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

app = Flask(__name__)

HOST = "0.0.0.0"
PORT = 9000

current_vector: List[float] = [0.0] * 64
last_ping = 0.0


def _listener() -> None:
    global current_vector, last_ping
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT))
    while True:
        data, _ = sock.recvfrom(8192)
        try:
            obj = json.loads(data.decode("utf-8"))
            if "ping" in obj:
                last_ping = time.time()
            vec = obj.get("emotions")
            if isinstance(vec, list) and len(vec) == 64:
                current_vector = [float(v) for v in vec]
        except Exception:
            continue


@app.route("/state")
def state() -> object:
    alive = time.time() - last_ping < 10
    return jsonify({"vector": current_vector, "alive": alive, "last_ping": last_ping})


@app.route("/")
def index() -> str:
    return """<html><body><h3>Emotion Vector</h3>
<script>
async function refresh(){
 const r=await fetch('/state');
 const j=await r.json();
 document.getElementById('status').textContent=j.alive?'alive':'missing';
 const cvs=document.getElementById('c');
 const ctx=cvs.getContext('2d');
 ctx.clearRect(0,0,cvs.width,cvs.height);
 const w=cvs.width/64;
 for(let i=0;i<64;i++){ctx.fillRect(i*w,cvs.height*(1-j.vector[i]),w-1,cvs.height*j.vector[i]);}
}
setInterval(refresh,1000);
</script>
<canvas id='c' width='640' height='200' style='border:1px solid #ccc'></canvas>
<div>Status: <span id='status'>?</span></div>
</body></html>"""


def run() -> None:
    require_admin_banner()
    threading.Thread(target=_listener, daemon=True).start()
    app.run(port=5005)


if __name__ == "__main__":  # pragma: no cover - manual
    run()
