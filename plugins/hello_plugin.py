"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Example GUI plugin adding a simple panel."""

from tkinter import Label, Frame
from gui_stub import CathedralGUI


def register(gui: CathedralGUI) -> None:
    frame = Frame()
    Label(frame, text="Hello Plugin").pack()
    gui.add_panel(frame)
