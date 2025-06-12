from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Avatar Presence Pulse Animation

Animates avatar presence intensity in sync with the presence pulse API.
Displays a tiny Tkinter gauge as a minimal GUI in addition to an ASCII bar.
"""
from logging_config import get_log_path

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

try:  # pragma: no cover - GUI optional
    import tkinter as tk
except Exception:  # pragma: no cover - headless env
    tk = None  # type: ignore[import-untyped]  # Tkinter optional on headless systems

from presence_pulse_api import pulse

LOG_PATH = get_log_path("avatar_animation.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_GUI_ROOT: Optional[tk.Tk] = None
_GUI_VAR: Optional[tk.DoubleVar] = None


def _ensure_gui(avatar: str) -> None:
    global _GUI_ROOT, _GUI_VAR
    if tk is None:
        return
    if _GUI_ROOT is None:
        _GUI_ROOT = tk.Tk()
        _GUI_ROOT.title(f"Pulse - {avatar}")
        _GUI_VAR = tk.DoubleVar(value=0)
        bar = tk.Scale(
            _GUI_ROOT,
            variable=_GUI_VAR,
            from_=0,
            to=1,
            resolution=0.01,
            orient="horizontal",
            length=200,
            showvalue=False,
        )
        bar.pack()


def animate_once(avatar: str) -> dict:
    p = pulse()
    _ensure_gui(avatar)
    if _GUI_VAR is not None:
        _GUI_VAR.set(p)
        _GUI_ROOT.update_idletasks()
        _GUI_ROOT.update()
    bar = "#" * int(p * 10)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "avatar": avatar,
        "pulse": p,
        "animation": bar,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description="Avatar presence pulse animation")
    ap.add_argument("avatar")
    args = ap.parse_args()
    entry = animate_once(args.avatar)
    print(entry["animation"])


if __name__ == "__main__":
    main()
