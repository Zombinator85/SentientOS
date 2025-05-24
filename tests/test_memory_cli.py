import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_cli_imports():
    import memory_cli
    assert hasattr(memory_cli, "main")
