"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


import os
import sys
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import importlib
import scripts.quota_reporter as qr

class DummyResp:
    def __init__(self, status=200):
        self.status_code = status
        self.headers = {}


def test_report(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(tmp_path / "logs"))
    importlib.reload(qr)
    log = qr.LOG_FILE
    log.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {"timestamp": "2024-01-01T10:00:00", "model": "gpt", "usage": {"total_tokens": 10}},
        {"timestamp": "2024-01-01T11:00:00", "model": "gpt", "usage": {"total_tokens": 5}},
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries))
    monkeypatch.chdir(tmp_path)
    sent = {}
    def fake_post(url, json):
        sent["url"] = url
        sent["text"] = json["text"]
        return DummyResp(200)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://example.com")
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    monkeypatch.setattr(qr.requests, "post", fake_post)
    ret = qr.main([])
    assert ret == 0
    assert "gpt" in sent["text"]
