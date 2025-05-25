import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import context_window as cw


def test_rolling_summary():
    cw.recent_messages.clear()
    cw.summary = ""
    for i in range(7):
        cw.add_message(f"msg{i}")
    recent, summary = cw.get_context()
    assert len(recent) <= cw.MAX_RECENT
    assert summary
