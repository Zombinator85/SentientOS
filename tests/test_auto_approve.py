import importlib
import builtins
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import auto_approve


def test_auto_approve_env(monkeypatch):
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    importlib.reload(auto_approve)
    assert auto_approve.is_auto_approve() is True
    assert auto_approve.prompt_yes_no("q?") is True


def test_prompt_yes_no_interactive(monkeypatch):
    monkeypatch.delenv("LUMOS_AUTO_APPROVE", raising=False)
    monkeypatch.setattr(builtins, "input", lambda _: "y")
    importlib.reload(auto_approve)
    assert auto_approve.is_auto_approve() is False
    assert auto_approve.prompt_yes_no("q?") is True
