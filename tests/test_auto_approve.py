import os
import sys
from importlib import reload


import sentientos.scripts.auto_approve as aa


def test_prompt_yes_no_interactive(monkeypatch):
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "")
    monkeypatch.setattr("builtins.input", lambda p: "y")
    reload(aa)
    assert aa.prompt_yes_no("continue?") is True


def test_prompt_yes_no_auto(monkeypatch):
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    reload(aa)
    assert aa.prompt_yes_no("continue?") is True

