"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.
import json
from importlib import reload
import os
import sys
import pytest


def test_load_and_query(tmp_path):
    log = tmp_path / "vision.jsonl"
    entries = [
        {"timestamp": 1.0, "faces": [{"id": 1, "emotions": {"happy": 0.8}, "dominant": "happy"}]},
        {"timestamp": 2.0, "faces": [{"id": 1, "emotions": {"happy": 0.3, "sad": 0.7}, "dominant": "sad"}]},
        {"timestamp": 3.0, "faces": []},  # Also tests empty faces are handled
    ]
    log.write_text("\n".join(json.dumps(e) for e in entries))

    import sentientos.emotion_dashboard as ed
    reload(ed)
    
    # Test log loader (should parse timeline, skip empty faces entry for id 1)
    data = ed.load_logs(log)
    assert 1 in data and len(data[1]) == 2
    # The empty faces line should not break the loader
    for d in data[1]:
        assert "timestamp" in d and "dominant" in d

    # Test querying closest state to a timestamp
    state = ed.query_state(data, 1, 2.0)
    assert state and state["dominant"] == "sad"
    # Query non-existent user or timestamp returns None
    assert ed.query_state(data, 99, 2.0) is None

def test_load_log_basic(tmp_path):
    # For backward compatibility with older loader
    log = tmp_path / 'vision.jsonl'
    log.write_text(json.dumps({'faces': []}) + '\n')
    import sentientos.emotion_dashboard as ed
    reload(ed)
    data = ed.load_logs(str(log))
    # Should return dict, but empty (no IDs)
    assert isinstance(data, dict)
