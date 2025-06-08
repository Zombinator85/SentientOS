from admin_utils import require_admin_banner, require_lumos_approval
import os
import sys

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_memory_cli_import():
    import memory_cli

    assert hasattr(memory_cli, "main")
