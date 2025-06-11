"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from admin_utils import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import sys
from importlib import reload

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import scripts.auto_approve as aa


def test_prompt_yes_no_interactive(monkeypatch):
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "")
    monkeypatch.setattr("builtins.input", lambda p: "y")
    reload(aa)
    assert aa.prompt_yes_no("continue?") is True


def test_prompt_yes_no_auto(monkeypatch):
    monkeypatch.setenv("LUMOS_AUTO_APPROVE", "1")
    reload(aa)
    assert aa.prompt_yes_no("continue?") is True

