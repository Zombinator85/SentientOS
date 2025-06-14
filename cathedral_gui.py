"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
"""Simple Tkinter GUI to configure LLM settings and launch the relay."""

from dotenv import load_dotenv
import asyncio
import os
import subprocess
import threading
from pathlib import Path
from tkinter import (
    Tk,
    Label,
    Entry,
    Button,
    OptionMenu,
    Text,
    Scrollbar,
    StringVar,
    Frame,
    Listbox,
    Spinbox,
    END,
)
from tkinter import ttk

import parliament_bus
from parliament_selector import ModelSelector

ENV_PATH = Path(".env")
load_dotenv(ENV_PATH)

MODEL_OPTIONS = [
    "openai/gpt-4o",
    "huggingface/mixtral",
    "local/deepseek",
]


class RelayGUI:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("SentientOS Cathedral GUI")
        self.proc: subprocess.Popen[str] | None = None

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True)

        relay_tab = Frame(nb)
        nb.add(relay_tab, text="Relay")

        parliament_tab = Frame(nb)
        nb.add(parliament_tab, text="Parliament")

        Label(relay_tab, text="OpenAI API Key").grid(row=0, column=0, sticky="w")
        self.key_var = StringVar(value=os.getenv("OPENAI_API_KEY", ""))
        Entry(relay_tab, textvariable=self.key_var, width=40).grid(row=0, column=1, sticky="we")

        Label(relay_tab, text="Model").grid(row=1, column=0, sticky="w")
        self.model_var = StringVar(value=os.getenv("MODEL_SLUG", MODEL_OPTIONS[0]))
        OptionMenu(relay_tab, self.model_var, *MODEL_OPTIONS).grid(row=1, column=1, sticky="we")

        Label(relay_tab, text="System Prompt").grid(row=2, column=0, sticky="nw")
        self.prompt_txt = Text(relay_tab, height=4, width=50)
        self.prompt_txt.grid(row=2, column=1, sticky="we")
        self.prompt_txt.insert("1.0", os.getenv("SYSTEM_PROMPT", ""))

        Button(relay_tab, text="Save", command=self.save).grid(row=3, column=0, pady=4)
        self.start_btn = Button(relay_tab, text="Start Relay", command=self.start_relay)
        self.start_btn.grid(row=3, column=1, sticky="w", pady=4)
        self.stop_btn = Button(relay_tab, text="Stop Relay", command=self.stop_relay, state="disabled")
        self.stop_btn.grid(row=3, column=1, sticky="e", pady=4)

        console = Frame(relay_tab)
        console.grid(row=4, column=0, columnspan=2, sticky="nsew")
        self.output = Text(console, height=12, state="disabled")
        self.output.pack(side="left", fill="both", expand=True)
        sb = Scrollbar(console, command=self.output.yview)
        sb.pack(side="right", fill="y")
        self.output.config(yscrollcommand=sb.set)

        relay_tab.grid_columnconfigure(1, weight=1)
        relay_tab.grid_rowconfigure(4, weight=1)

        # parliament tab widgets
        self.selector = ModelSelector(MODEL_OPTIONS)
        Label(parliament_tab, text="Models (drag to reorder)").pack(anchor="w")
        self.model_list = Listbox(parliament_tab, exportselection=False)
        for m in self.selector.models:
            self.model_list.insert(END, m)
        self.model_list.pack(fill="both", expand=True, padx=2, pady=2)
        self.model_list.bind("<ButtonPress-1>", self._drag_start)
        self.model_list.bind("<B1-Motion>", self._drag_move)

        Label(parliament_tab, text="Cycles").pack(anchor="w")
        self.cycle_var = StringVar(value="1")
        self.cycle_spin = Spinbox(parliament_tab, from_=1, to=99, textvariable=self.cycle_var, width=5)
        self.cycle_spin.pack(anchor="w")

        Button(parliament_tab, text="Summon", command=self.send_request).pack(pady=4)

        self._drag_index: int | None = None

    def _drag_start(self, event: object) -> None:
        self._drag_index = self.model_list.nearest(event.y)

    def _drag_move(self, event: object) -> None:
        if self._drag_index is None:
            return
        i = self.model_list.nearest(event.y)
        if i == self._drag_index:
            return
        item = self.model_list.get(self._drag_index)
        self.model_list.delete(self._drag_index)
        self.model_list.insert(i, item)
        self.selector.move(self._drag_index, i)
        self._drag_index = i

    def send_request(self) -> None:
        models = self.selector.get_models()
        cycles = int(self.cycle_var.get() or 1)
        data = {"event_type": "parliament_request", "models": models, "cycles": cycles}
        asyncio.run(parliament_bus.bus.publish(data))
        self.log("Parliament request sent.")

    def log(self, msg: str) -> None:
        self.output.configure(state="normal")
        self.output.insert(END, msg + "\n")
        self.output.see(END)
        self.output.configure(state="disabled")

    def save(self) -> None:
        env = {
            "OPENAI_API_KEY": self.key_var.get(),
            "MODEL_SLUG": self.model_var.get(),
            "SYSTEM_PROMPT": self.prompt_txt.get("1.0", END).strip(),
        }
        lines = []
        if ENV_PATH.exists():
            lines = ENV_PATH.read_text().splitlines()
        remaining = set(env)
        out_lines: list[str] = []
        for line in lines:
            if not line or line.startswith("#"):
                out_lines.append(line)
                continue
            k, _, _ = line.partition("=")
            if k in env:
                out_lines.append(f"{k}={env[k]}")
                remaining.remove(k)
            else:
                out_lines.append(line)
        for k in remaining:
            out_lines.append(f"{k}={env[k]}")
        ENV_PATH.write_text("\n".join(out_lines))
        load_dotenv(ENV_PATH, override=True)

    def start_relay(self) -> None:
        if self.proc:
            return
        self.save()
        self.log("Starting relay…")
        self.proc = subprocess.Popen(
            ["python", "sentient_api.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        threading.Thread(target=self._stream_output, daemon=True).start()

    def _stream_output(self) -> None:
        assert self.proc is not None
        if self.proc.stdout is None:
            return
        for line in self.proc.stdout:
            self.log(line.rstrip())
        self.stop_relay()

    def stop_relay(self) -> None:
        if self.proc:
            self.proc.terminate()
            self.proc = None
            self.log("Relay stopped.")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")


def main() -> None:
    root = Tk()
    RelayGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
