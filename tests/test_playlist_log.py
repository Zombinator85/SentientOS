"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import json
import os
import sys
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger


def test_playlist_log_reason():
    log = ledger.playlist_log([{"file": "a"}], "Joy", "u", "local", reason="trend")
    assert log["reason"] == "trend"

