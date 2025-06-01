import json
import os
import sys
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger


def test_playlist_log_reason():
    log = ledger.playlist_log([{"file": "a"}], "Joy", "u", "local", reason="trend")
    assert log["reason"] == "trend"

