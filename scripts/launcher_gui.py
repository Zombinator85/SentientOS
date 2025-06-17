from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Simple GUI launcher for SentientOS."""

import os
import subprocess
from pathlib import Path
from typing import List

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover - headless
    tk = None  # type: ignore
    ttk = None  # type: ignore

LOG_PATH = Path("logs/launch_sentientos.log")


def _read_log_lines(limit: int = 20) -> str:
    if not LOG_PATH.exists():
        return "No launch history."
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    return "\n".join(lines)


def _launch(flags: List[str]) -> None:
    cmd = ["start", "cmd", "/k", "launch_sentientos.bat"] + flags
    if os.name == "nt":
        subprocess.Popen(" ".join(cmd), shell=True)
    else:  # pragma: no cover - windows only
        subprocess.Popen(["bash", "-c", " ".join(cmd)])


def main() -> None:  # pragma: no cover - manual
    if tk is None:
        print("Tkinter not available")
        return

    root = tk.Tk()
    root.title("SentientOS Launcher")

    mode_var = tk.StringVar(value="gui")
    debug_var = tk.BooleanVar(value=False)
    safe_var = tk.BooleanVar(value=False)

    frm = ttk.Frame(root, padding=10)
    frm.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frm, text="Launch Mode:").pack(anchor=tk.W)
    for val, lbl in [("gui", "GUI"), ("headless", "Headless")]:
        ttk.Radiobutton(frm, text=lbl, variable=mode_var, value=val).pack(anchor=tk.W)

    ttk.Checkbutton(frm, text="Debug", variable=debug_var).pack(anchor=tk.W)
    ttk.Checkbutton(frm, text="Safe Mode", variable=safe_var).pack(anchor=tk.W)

    log_box = tk.Text(frm, height=10, width=60)
    log_box.insert(tk.END, _read_log_lines())
    log_box.config(state=tk.DISABLED)
    log_box.pack(fill=tk.BOTH, expand=True, pady=5)

    def launch_and_quit() -> None:
        flags: List[str] = []
        if mode_var.get() == "headless":
            flags.append("--headless")
        if debug_var.get():
            flags.append("--debug")
        if safe_var.get():
            flags.append("--safe")
        root.withdraw()
        _launch(flags)
        root.after(1000, root.destroy)

    ttk.Button(frm, text="Launch", command=launch_and_quit).pack(pady=5)
    ttk.Button(frm, text="Exit", command=root.destroy).pack()

    root.mainloop()


if __name__ == "__main__":
    main()
