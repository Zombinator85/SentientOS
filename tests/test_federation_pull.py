"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import types

import scripts.federation_puller as fp


def test_puller_writes_log(tmp_path, monkeypatch):
    log = tmp_path / "federation_log.jsonl"
    peer = "http://node1/presence"
    data = [
        {"dialogue_id": "a", "agents": ["x"], "end_ts": 1.0},
        {"dialogue_id": "b", "agents": ["y"], "end_ts": 2.0},
    ]

    class DummyResp:
        def __init__(self, payload):
            self.payload = payload
        def raise_for_status(self):
            return None
        def json(self):
            return self.payload

    def fake_get(url, timeout=5):
        assert url == peer
        return DummyResp(data)

    monkeypatch.setattr(fp, "LOG_PATH", log)
    monkeypatch.setattr(fp, "requests", types.SimpleNamespace(get=fake_get))

    seen: set[tuple[str, str]] = set()
    fp.poll_peers([peer], log_path=log, seen=seen)
    fp.poll_peers([peer], log_path=log, seen=seen)

    lines = log.read_text().splitlines()
    assert len(lines) == 2
    entries = [json.loads(l) for l in lines]
    assert all(e["source"] == peer for e in entries)
