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
import tkinter.messagebox as messagebox
from typing import Tuple

from urllib.parse import urlparse

from emotions import EMOTIONS

import parliament_bus
from parliament_selector import ModelSelector

ENV_PATH = Path(".env")
load_dotenv(ENV_PATH)

MODEL_OPTIONS = [
    "mixtral",
    "openai/gpt-4o",
    "deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free",
]

EMOTION_CHOICES = EMOTIONS[:8]


def validate_settings(model: str, api_key: str, endpoint: str) -> Tuple[bool, str]:
    """Return (True, '') if settings valid else (False, reason)."""
    if not endpoint.startswith("http"):
        return False, "Endpoint must start with http"
    if model.startswith("openai/") and not api_key:
        return False, "OPENAI_API_KEY required for OpenAI models"
    if model not in MODEL_OPTIONS:
        return False, "Unsupported model"
    try:
        urlparse(endpoint)
    except Exception:
        return False, "Invalid URL"
    return True, ""


class RelayGUI:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("SentientOS Cathedral GUI")
        self.proc: subprocess.Popen[str] | None = None
        self.bridge_proc: subprocess.Popen[str] | None = None

        self.status_lbl = Label(root, text="Relay stopped")
        self.status_lbl.pack(anchor="w")

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True)

        relay_tab = Frame(nb)
        nb.add(relay_tab, text="Relay")

        parliament_tab = Frame(nb)
        nb.add(parliament_tab, text="Parliament")

        Label(relay_tab, text="OpenAI API Key").grid(row=0, column=0, sticky="w")
        self.key_var = StringVar(value=os.getenv("OPENAI_API_KEY", ""))
        Entry(relay_tab, textvariable=self.key_var, width=40).grid(row=0, column=1, sticky="we")

        Label(relay_tab, text="Relay Endpoint").grid(row=1, column=0, sticky="w")
        self.url_var = StringVar(value=os.getenv("RELAY_URL", "http://localhost:5000/relay"))
        Entry(relay_tab, textvariable=self.url_var, width=40).grid(row=1, column=1, sticky="we")

        Label(relay_tab, text="Model").grid(row=2, column=0, sticky="w")
        self.model_var = StringVar(value=os.getenv("MODEL_SLUG", MODEL_OPTIONS[0]))
        OptionMenu(relay_tab, self.model_var, *MODEL_OPTIONS).grid(row=2, column=1, sticky="we")

        Label(relay_tab, text="Emotion").grid(row=3, column=0, sticky="w")
        self.emotion_var = StringVar(value=EMOTION_CHOICES[0])
        OptionMenu(relay_tab, self.emotion_var, *EMOTION_CHOICES).grid(row=3, column=1, sticky="we")

        Label(relay_tab, text="System Prompt").grid(row=4, column=0, sticky="nw")
        self.prompt_txt = Text(relay_tab, height=4, width=50)
        self.prompt_txt.grid(row=4, column=1, sticky="we")
        self.prompt_txt.insert("1.0", os.getenv("SYSTEM_PROMPT", ""))

        self.prompt_entry = Text(relay_tab, height=2, width=50)
        self.prompt_entry.grid(row=5, column=1, sticky="we")
        Label(relay_tab, text="Test Prompt").grid(row=5, column=0, sticky="nw")
        Button(relay_tab, text="Send", command=self.send_test).grid(row=5, column=2, padx=2)

        Button(relay_tab, text="Save", command=self.save).grid(row=6, column=0, pady=4)
        self.start_btn = Button(relay_tab, text="Start Relay", command=self.start_relay)
        self.start_btn.grid(row=6, column=1, sticky="w", pady=4)
        self.stop_btn = Button(relay_tab, text="Stop Relay", command=self.stop_relay, state="disabled")
        self.stop_btn.grid(row=6, column=1, sticky="e", pady=4)
        Button(relay_tab, text="Edit .env", command=self.edit_env).grid(row=6, column=2, padx=2)
        Button(relay_tab, text="Regenerate Config", command=self.sync_env).grid(row=7, column=0, columnspan=2, sticky="we")
        Button(relay_tab, text="Export Logs", command=self.export_logs).grid(row=7, column=2, padx=2)

        console = Frame(relay_tab)
        console.grid(row=8, column=0, columnspan=3, sticky="nsew")
        self.output = Text(console, height=12, state="disabled")
        self.output.pack(side="left", fill="both", expand=True)
        sb = Scrollbar(console, command=self.output.yview)
        sb.pack(side="right", fill="y")
        self.output.config(yscrollcommand=sb.set)

        relay_tab.grid_columnconfigure(1, weight=1)
        relay_tab.grid_rowconfigure(8, weight=1)

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

    def send_test(self) -> None:
        prompt = self.prompt_entry.get("1.0", END).strip()
        ok, msg = validate_settings(self.model_var.get(), self.key_var.get(), self.url_var.get())
        if not ok:
            messagebox.showerror("Invalid settings", msg)
            return
        try:
            import model_bridge

            result = model_bridge.send_message(prompt, emotion=self.emotion_var.get(), emit=False)
            self.log("Response: " + result.get("response", ""))
        except Exception as e:  # pragma: no cover - runtime issues
            self.log(f"Error: {e}")

    def log(self, msg: str) -> None:
        self.output.configure(state="normal")
        self.output.insert(END, msg + "\n")
        self.output.see(END)
        self.output.configure(state="disabled")

    def edit_env(self) -> None:  # pragma: no cover - interactive
        editor = os.getenv("EDITOR", "nano")
        subprocess.Popen([editor, str(ENV_PATH)])

    def sync_env(self) -> None:
        try:
            subprocess.run(["python", "scripts/env_sync_autofill.py"], check=True)
            self.log("Config regenerated")
        except Exception as e:
            self.log(f"Config generation failed: {e}")

    def export_logs(self) -> None:
        import zipfile

        dest = Path("logs_export.zip")
        with zipfile.ZipFile(dest, "w") as z:
            for path in Path("logs").rglob("*"):
                if path.is_file():
                    z.write(path)
            for path in Path(os.getenv("MEMORY_DIR", "logs/memory")).rglob("*"):
                if path.is_file():
                    z.write(path)
        self.log(f"Logs exported to {dest}")

    def save(self) -> None:
        ok, msg = validate_settings(self.model_var.get(), self.key_var.get(), self.url_var.get())
        if not ok:
            messagebox.showerror("Invalid settings", msg)
            return
        env = {
            "OPENAI_API_KEY": self.key_var.get(),
            "MODEL_SLUG": self.model_var.get(),
            "SYSTEM_PROMPT": self.prompt_txt.get("1.0", END).strip(),
            "RELAY_URL": self.url_var.get(),
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
        if not self.bridge_proc:
            self.bridge_proc = subprocess.Popen(
                ["python", "model_bridge.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            threading.Thread(target=self._stream_output_bridge, daemon=True).start()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_lbl.config(text="Relay running")
        threading.Thread(target=self._stream_output, daemon=True).start()

    def _stream_output(self) -> None:
        assert self.proc is not None
        if self.proc.stdout is None:
            return
        for line in self.proc.stdout:
            self.log(line.rstrip())
        self.stop_relay()

    def _stream_output_bridge(self) -> None:
        assert self.bridge_proc is not None
        if self.bridge_proc.stdout is None:
            return
        for line in self.bridge_proc.stdout:
            self.log("[bridge] " + line.rstrip())

    def stop_relay(self) -> None:
        if self.proc:
            self.proc.terminate()
            self.proc = None
            self.log("Relay stopped.")
        if self.bridge_proc:
            self.bridge_proc.terminate()
            self.bridge_proc = None
            self.log("Bridge stopped.")
        self.status_lbl.config(text="Relay stopped")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")


def main() -> None:
    root = Tk()
    RelayGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
