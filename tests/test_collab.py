import threading
import time
import json
from urllib import request, parse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from collab_server import run


def start_server():
    run(port=5050)


def test_broadcast(tmp_path):
    thread = threading.Thread(target=start_server, daemon=True)
    thread.start()
    time.sleep(1)

    data = parse.urlencode({"id": "c1"}).encode()
    request.urlopen("http://localhost:5050/connect", data=data)
    data = parse.urlencode({"id": "c2"}).encode()
    request.urlopen("http://localhost:5050/connect", data=data)
    req = request.Request(
        "http://localhost:5050/edit",
        data=json.dumps({"chapter": 1, "text": "hi"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    request.urlopen(req)
    time.sleep(0.2)
    with request.urlopen("http://localhost:5050/poll") as r:
        recv = json.loads(r.read().decode())
    data = parse.urlencode({"id": "c1"}).encode()
    request.urlopen("http://localhost:5050/disconnect", data=data)
    data = parse.urlencode({"id": "c2"}).encode()
    request.urlopen("http://localhost:5050/disconnect", data=data)
    assert recv and recv[0]["text"] == "hi"





