"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from __future__ import annotations


import os
import sys


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_memory_cli_import():
    import memory_cli

    assert hasattr(memory_cli, "main")
