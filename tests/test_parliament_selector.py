"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import parliament_selector as ps


def test_move_down():
    sel = ps.ModelSelector(["a", "b", "c"])
    sel.move(0, 2)
    assert sel.get_models() == ["b", "c", "a"]


def test_move_up():
    sel = ps.ModelSelector(["a", "b", "c"])
    sel.move(2, 0)
    assert sel.get_models() == ["c", "a", "b"]

def test_invalid_move():
    sel = ps.ModelSelector(["a", "b"])
    sel.move(5, 1)
    assert sel.get_models() == ["a", "b"]
