"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import json
import importlib
from pathlib import Path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import treasury_federation as tf
import federation_log as fl
import ledger
import pytest

import sentient_banner as sb


def test_invite(tmp_path, monkeypatch):
    path = tmp_path / 'fed.jsonl'
    def fake_append(p: Path, entry: dict):
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
        return entry

    monkeypatch.setattr(ledger, '_append', fake_append)
    monkeypatch.setattr(sb, 'print_banner', lambda: None)
    monkeypatch.setattr(sb, 'print_closing', lambda: None)
    importlib.reload(fl)
    importlib.reload(tf)
    tf.invite('peer1', email='a@example.com', blessing='hi', supporter='bob', affirm=True)
    data = path.read_text().splitlines()
    assert len(data) == 3
    assert 'peer1' in data[0]
