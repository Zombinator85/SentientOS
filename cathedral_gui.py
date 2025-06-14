"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
"""Simple Tkinter GUI to configure LLM settings and launch the relay."""

from dotenv import load_dotenv
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
    END,
)

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

        Label(root, text="OpenAI API Key").grid(row=0, column=0, sticky="w")
        self.key_var = StringVar(value=os.getenv("OPENAI_API_KEY", ""))
        Entry(root, textvariable=self.key_var, width=40).grid(row=0, column=1, sticky="we")

        Label(root, text="Model").grid(row=1, column=0, sticky="w")
        self.model_var = StringVar(value=os.getenv("MODEL_SLUG", MODEL_OPTIONS[0]))
        OptionMenu(root, self.model_var, *MODEL_OPTIONS).grid(row=1, column=1, sticky="we")

        Label(root, text="System Prompt").grid(row=2, column=0, sticky="nw")
        self.prompt_txt = Text(root, height=4, width=50)
        self.prompt_txt.grid(row=2, column=1, sticky="we")
        self.prompt_txt.insert("1.0", os.getenv("SYSTEM_PROMPT", ""))

        Button(root, text="Save", command=self.save).grid(row=3, column=0, pady=4)
        self.start_btn = Button(root, text="Start Relay", command=self.start_relay)
        self.start_btn.grid(row=3, column=1, sticky="w", pady=4)
        self.stop_btn = Button(root, text="Stop Relay", command=self.stop_relay, state="disabled")
        self.stop_btn.grid(row=3, column=1, sticky="e", pady=4)

        console = Frame(root)
        console.grid(row=4, column=0, columnspan=2, sticky="nsew")
        self.output = Text(console, height=12, state="disabled")
        self.output.pack(side="left", fill="both", expand=True)
        sb = Scrollbar(console, command=self.output.yview)
        sb.pack(side="right", fill="y")
        self.output.config(yscrollcommand=sb.set)

        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(4, weight=1)

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
