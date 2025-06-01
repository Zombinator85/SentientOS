import os
import json
import importlib
from pathlib import Path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import treasury_federation as tf
import federation_log as fl
import ledger


def test_invite(tmp_path, monkeypatch):
    path = tmp_path / 'fed.jsonl'
    def fake_append(p: Path, entry: dict):
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
        return entry

    monkeypatch.setattr(ledger, '_append', fake_append)
    importlib.reload(fl)
    importlib.reload(tf)
    tf.invite('peer1', email='a@example.com')
    data = path.read_text()
    assert 'peer1' in data
