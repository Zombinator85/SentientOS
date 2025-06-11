import json
import os
import sys
from pathlib import Path

import sentientos.ledger as ledger


def test_playlist_log_reason():
    log = ledger.playlist_log([{"file": "a"}], "Joy", "u", "local", reason="trend")
    assert log["reason"] == "trend"

