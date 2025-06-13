"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()

import importlib
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import cathedral_launcher as cl


def test_placeholder(monkeypatch):
    # Simulate torch with GPU
    class Torch:
        class cuda:
            @staticmethod
            def is_available() -> bool:
                return True
    monkeypatch.setitem(sys.modules, 'torch', Torch)
    importlib.reload(cl)
    assert cl.check_gpu()

    # Simulate torch without GPU
    class TorchNo:
        class cuda:
            @staticmethod
            def is_available() -> bool:
                return False
    monkeypatch.setitem(sys.modules, 'torch', TorchNo)
    importlib.reload(cl)
    assert not cl.check_gpu()


def test_env_file_created(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.example").write_text("EXAMPLE=1")
    env = cl.ensure_env_file()
    assert env.exists()
    assert env.read_text() == "EXAMPLE=1"


def test_log_dir_created(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = cl.ensure_log_dir()
    assert path.exists()