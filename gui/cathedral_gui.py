"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Streamlit-based control panel with Tkinter fallback."""

import os
import sys
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import json
from gui import wdm_panel

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover - optional
    requests = None  # type: ignore

try:
    import streamlit as st  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional
    st = None  # type: ignore

try:
    from tkinter import Tk, Label, Text, Button, END
except Exception:  # pragma: no cover - optional
    Tk = None  # type: ignore

try:
    import demo_recorder  # type: ignore
except Exception:  # pragma: no cover - optional
    demo_recorder = None  # type: ignore[misc]

_RECORDER: Optional[demo_recorder.DemoRecorder] | None = None  # type: ignore[attr-defined]


_API_PROC: Optional[subprocess.Popen[str]] = None
_BRIDGE_PROC: Optional[subprocess.Popen[str]] = None
_LOGS: list[str] = []


def _stream_output(proc: subprocess.Popen[str], name: str) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        _LOGS.append(f"[{name}] {line.rstrip()}")


def launch_processes() -> None:
    """Launch or reconnect to sentient_api.py and model_bridge.py."""
    global _API_PROC, _BRIDGE_PROC
    if _API_PROC is None or _API_PROC.poll() is not None:
        _API_PROC = subprocess.Popen(
            [sys.executable, "sentient_api.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        threading.Thread(target=_stream_output, args=(_API_PROC, "api"), daemon=True).start()
        _LOGS.append("sentient_api launched")
    if _BRIDGE_PROC is None or _BRIDGE_PROC.poll() is not None:
        _BRIDGE_PROC = subprocess.Popen(
            [sys.executable, "model_bridge.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        threading.Thread(target=_stream_output, args=(_BRIDGE_PROC, "bridge"), daemon=True).start()
        _LOGS.append("model_bridge launched")


def fetch_status(url: str = "http://localhost:5000/status") -> Dict[str, Any]:
    """Return status info from the relay."""
    if requests is None:
        return {"uptime": "n/a", "last_heartbeat": "n/a"}
    try:
        resp = requests.get(url, timeout=2)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {"uptime": "unknown", "last_heartbeat": "unknown"}


def run_streamlit() -> None:
    if st is None:
        print("Streamlit not available. Falling back to Tkinter.")
        run_tkinter()
        return

    st.set_page_config(page_title="Cathedral GUI")
    sidebar = st.sidebar
    page = sidebar.selectbox("Panel", ["Control", "WDM"])

    entry = None
    path = Path("logs/presence.jsonl")
    if path.exists():
        lines = path.read_text().splitlines()
        if lines:
            try:
                entry = json.loads(lines[-1])
            except Exception:
                entry = None
    if entry:
        ts = entry.get("end_ts")
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "unknown"
        sidebar.write(f"Last WDM Run: {entry.get('dialogue_id')} {ts_str}")
        agents = ", ".join(entry.get("agents", []))
        sidebar.write(f"Active agents: {agents}")

    active_start = None
    stream_path = Path("logs/presence_stream.jsonl")
    if stream_path.exists():
        state: Dict[str, float] = {}
        for line in stream_path.read_text().splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            did = ev.get("dialogue_id")
            if ev.get("event") == "start" and did:
                state[did] = ev.get("ts", 0.0)
            elif ev.get("event") == "end" and did in state:
                state.pop(did, None)
        if state:
            active_start = sorted(state.values())[0]
    if active_start is not None:
        elapsed = int(time.time() - active_start)
        sidebar.write(f"Active now ({elapsed}s)")

    if page == "WDM":
        wdm_panel.render()
        return
    st.title("Cathedral Control Panel")

    if st.button("Launch/Reconnect"):
        launch_processes()

    if st.button("\u25cf Record"):
        global _RECORDER
        if demo_recorder is None:
            st.error("Recorder unavailable")
        else:
            if _RECORDER is None or not _RECORDER.running:
                _RECORDER = demo_recorder.DemoRecorder()
                _RECORDER.start()
                _LOGS.append("Recording started")
            else:
                _RECORDER.stop()
                path = _RECORDER.export()
                _LOGS.append(f"Saved {path}")
                st.success(f"Saved {path}")

    status = fetch_status()
    st.write(f"Uptime: {status.get('uptime')}")
    st.write(f"Heartbeat: {status.get('last_heartbeat')}")

    st.subheader("Startup Logs")
    st.text_area("logs", "\n".join(_LOGS), height=200)

    st.subheader("Avatar Connections")
    st.write("(placeholder for future sockets)")


def run_tkinter() -> None:  # pragma: no cover - interactive fallback
    if Tk is None:
        print("Tkinter not available.")
        return
    root = Tk()
    root.title("Cathedral Control Panel")
    lbl = Label(root, text="Status")
    lbl.pack()
    log_box = Text(root, height=10)
    log_box.pack()

    def refresh() -> None:
        status = fetch_status()
        lbl.config(text=f"Uptime: {status.get('uptime')} Heartbeat: {status.get('last_heartbeat')}")
        log_box.delete("1.0", END)
        log_box.insert(END, "\n".join(_LOGS))
        root.after(2000, refresh)

    Button(root, text="Launch/Reconnect", command=launch_processes).pack()
    if demo_recorder is not None:
        rec = demo_recorder.DemoRecorder()
        rec_btn = Button(root, text="\u25cf Record")

        def toggle() -> None:
            if rec.running:
                rec.stop()
                path = rec.export()
                rec_btn.config(text="\u25cf Record")
                _LOGS.append(f"Saved {path}")
                lbl.config(text=f"Saved {path.name}")
            else:
                rec.start()
                rec_btn.config(text="Stop")
                lbl.config(text="Recording…")

        rec_btn.config(command=toggle)
        rec_btn.pack()
    refresh()
    root.mainloop()


def main() -> None:  # pragma: no cover - manual
    if st is not None:
        run_streamlit()
    else:
        run_tkinter()


if __name__ == "__main__":  # pragma: no cover - manual
    main()
