from pathlib import Path
from fastapi.testclient import TestClient
from api import federation_stream_api

def test_federation_stream(tmp_path, monkeypatch):
    log = tmp_path / "federation_stream.jsonl"
    log.write_text(
        '{"event": "start", "dialogue_id": "a", "ts": 1}\n'
        '{"event": "end", "dialogue_id": "a", "ts": 2}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(federation_stream_api, "LOG_PATH", log)
    monkeypatch.setattr(federation_stream_api, "require_admin_banner", lambda: None)
    monkeypatch.setattr(federation_stream_api, "require_lumos_approval", lambda: None)

    def finite_stream(path: Path):
        for record in path.read_text(encoding="utf-8").splitlines():
            yield f"data: {record}\n\n"

    monkeypatch.setattr(federation_stream_api, "stream_events", finite_stream)
    client = TestClient(federation_stream_api.app)
    resp = client.get("/federation/stream")
    assert resp.headers["content-type"].startswith("text/event-stream")
    lines = resp.text.splitlines()
    assert any("\"start\"" in l for l in lines)
    assert any("\"end\"" in l for l in lines)
