"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
memory_tail = pytest.importorskip("memory_tail")


def test_memory_tail_help(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["mt", "--help"])
    with pytest.raises(SystemExit):
        memory_tail.main()


