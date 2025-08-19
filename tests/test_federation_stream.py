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
    client = TestClient(federation_stream_api.app)
    with client.stream("GET", "/federation/stream") as resp:
        lines = []
        for line in resp.iter_lines():
            if line:
                lines.append(line.decode())
            if len(lines) >= 2:
                break
    assert any("\"start\"" in l for l in lines)
    assert any("\"end\"" in l for l in lines)
