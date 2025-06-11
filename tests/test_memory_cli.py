"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
import os
import sys




def test_memory_cli_import():
    import sentientos.memory_cli as memory_cli

    assert hasattr(memory_cli, "main")
