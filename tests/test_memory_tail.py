import os
import sys


import pytest
memory_tail = pytest.importorskip("memory_tail")


def test_memory_tail_help(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["mt", "--help"])
    with pytest.raises(SystemExit):
        memory_tail.main()


