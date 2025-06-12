"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import importlib
import os
import sys
from pathlib import Path
import requests
import sys
sys.modules['requests'] = requests
import requests_mock
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

@pytest.mark.network
def test_ping_peer(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, 'requests', requests)
    import federation_handshake as fh
    importlib.reload(fh)
    log = tmp_path / "handshake.jsonl"
    monkeypatch.setattr(fh, 'LEDGER', log)
    url = 'http://peer/ping'
    with requests_mock.Mocker() as m:
        m.get(url, status_code=200)
        entry = fh.ping_peer(url)
    assert entry['status'] == '200'
    assert log.exists()

@pytest.mark.network
def test_webhook_alert(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, 'requests', requests)
    monkeypatch.setenv('TELEGRAM_WEBHOOKS', '')
    monkeypatch.setenv('TELEGRAM_TOKEN', 'tok')
    monkeypatch.setenv('TELEGRAM_ADMIN', '1')
    import webhook_status_monitor as wsm
    importlib.reload(wsm)
    log = tmp_path / 'webhook.jsonl'
    monkeypatch.setattr(wsm, 'LOG_FILE', log)
    url = 'http://peer/hook'
    with requests_mock.Mocker() as m:
        m.get(url, status_code=500)
        post_mock = m.post('https://api.telegram.org/bottok/sendMessage', status_code=200)
        status = wsm._check(url)
        assert status == 500
        wsm._send_alert(url, status)
    assert post_mock.called

