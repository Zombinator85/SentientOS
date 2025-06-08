import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
try:
    import memory_tail
except Exception:
    memory_tail = None


def test_memory_tail_help(monkeypatch):
    if memory_tail is None:
        pytest.skip("memory_tail dependencies missing")
    monkeypatch.setattr(sys, "argv", ["mt", "--help"])
    with pytest.raises(SystemExit):
        memory_tail.main()


