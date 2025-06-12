"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Simple Tkinter app to visualize emotion vectors from UDP."""
import json
import os
import socket
import threading
import tkinter as tk

HOST = os.getenv("EMO_VIS_HOST", "0.0.0.0")
PORT = int(os.getenv("EMO_VIS_PORT", "9000"))


class Visualizer:
    def __init__(self) -> None:
        self.vec = [0.0] * 64
        self.root = tk.Tk()
        self.root.title("Emotion Vector")
        self.bars = []
        for i in range(64):
            var = tk.DoubleVar(value=0)
            bar = tk.Scale(
                self.root,
                variable=var,
                from_=0,
                to=1,
                resolution=0.01,
                orient="vertical",
                showvalue=False,
                length=100,
            )
            bar.grid(row=0, column=i)
            self.bars.append((var, bar))
        threading.Thread(target=self.listen, daemon=True).start()
        self.update_gui()
        self.root.mainloop()

    def listen(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((HOST, PORT))
        while True:
            data, _ = sock.recvfrom(8192)
            try:
                obj = json.loads(data.decode("utf-8"))
                vec = obj.get("emotions")
                if isinstance(vec, list) and len(vec) == 64:
                    self.vec = [float(v) for v in vec]
            except Exception:
                continue

    def update_gui(self) -> None:
        for (var, _), val in zip(self.bars, self.vec):
            var.set(val)
        self.root.after(500, self.update_gui)


if __name__ == "__main__":  # pragma: no cover - manual
    Visualizer()
