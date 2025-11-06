import importlib
import json
import sys
import types


def _reload(monkeypatch):
    psutil_stub = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "psutil", psutil_stub)
    module = importlib.import_module("relay_app")
    return importlib.reload(module)


def test_webrtc_session_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VOICE_ENABLED", "1")
    monkeypatch.setenv("NODE_TOKEN", "voice-token")
    module = _reload(monkeypatch)
    module.NODE_TOKEN = "voice-token"

    offer_payload = {"offer": {"type": "offer", "sdp": "dummy"}}
    module.request = types.SimpleNamespace(
        headers={"X-Node-Token": "voice-token"},
        remote_addr="127.0.0.1",
        cookies={},
        get_json=lambda: offer_payload,
        host="localhost",
    )
    created = module.webrtc_create()
    if hasattr(created, "get_json"):
        session = created.get_json()
    else:
        payload = created.data if hasattr(created, "data") else created
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        session = json.loads(payload)
    assert "session_id" in session

    ice_payload = {
        "session_id": session["session_id"],
        "candidate": {"candidate": "candidate:0 1 UDP 2122252543 0.0.0.0 9 typ host"},
    }
    module.request = types.SimpleNamespace(
        headers={"X-Node-Token": "voice-token"},
        remote_addr="127.0.0.1",
        cookies={},
        get_json=lambda: ice_payload,
        host="localhost",
    )
    updated = module.webrtc_add_ice()
    if hasattr(updated, "get_json"):
        data = updated.get_json()
    else:
        payload = updated.data if hasattr(updated, "data") else updated
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        data = json.loads(payload)
    assert data["ice_candidates"]
