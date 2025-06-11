"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import threading
import time
import json
import threading
from urllib import request, parse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from collab_server import run


def start_server(port=5050):
    run(port=port)


def test_broadcast(tmp_path):
    thread = threading.Thread(target=start_server, args=(5050,), daemon=True)
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


def test_presence(tmp_path):
    thread = threading.Thread(target=start_server, args=(5051,), daemon=True)
    thread.start()
    time.sleep(1)

    data = parse.urlencode({"id": "c1", "persona": "A"}).encode()
    request.urlopen("http://localhost:5051/connect", data=data)
    data = parse.urlencode({"id": "c2", "persona": "B"}).encode()
    request.urlopen("http://localhost:5051/connect", data=data)
    req = request.Request(
        "http://localhost:5051/update",
        data=json.dumps({"id": "c1", "chapter": 2}).encode(),
        headers={"Content-Type": "application/json"},
    )
    request.urlopen(req)
    with request.urlopen("http://localhost:5051/presence") as r:
        pres = json.loads(r.read().decode()).get("users", [])
    assert any(p.get("persona") == "A" and p.get("chapter") == 2 for p in pres)





