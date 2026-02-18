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
from sentientos.contract_sentinel import ContractSentinel
from sentientos.forge_daemon import _load_policy
from sentientos.forge_index import rebuild_index
from sentientos.forge_queue import ForgeQueue, ForgeRequest
from sentientos.forge_status import compute_status

requests: Any = None
try:
    import requests as _requests

    requests = _requests
except Exception:  # pragma: no cover - optional
    pass

st: Any = None
try:
    import streamlit as _st

    st = _st
except Exception:  # pragma: no cover - optional
    pass

Tk: Any = None
Label: Any = None
Text: Any = None
Button: Any = None
END: Any = None
try:
    from tkinter import Tk as _Tk, Label as _Label, Text as _Text, Button as _Button, END as _END

    Tk = _Tk
    Label = _Label
    Text = _Text
    Button = _Button
    END = _END
except Exception:  # pragma: no cover - optional
    pass

try:
    import demo_recorder
except Exception:  # pragma: no cover - optional
    demo_recorder = None

_RECORDER: Any | None = None


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


def fetch_status(url: str = "http://localhost:3928/status") -> Dict[str, Any]:
    """Return status info from the relay."""
    if requests is None:
        return {"uptime": "n/a", "last_heartbeat": "n/a"}
    try:
        resp = requests.get(url, timeout=2)
        resp.raise_for_status()
        payload = resp.json()
        return payload if isinstance(payload, dict) else {"uptime": "unknown", "last_heartbeat": "unknown"}
    except Exception:
        return {"uptime": "unknown", "last_heartbeat": "unknown"}


def run_streamlit() -> None:
    if st is None:
        print("Streamlit not available. Falling back to Tkinter.")
        run_tkinter()
        return

    st.set_page_config(page_title="Cathedral GUI")
    sidebar = st.sidebar
    page = sidebar.selectbox("Panel", ["Control", "WDM", "Forge"])

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

    fed_stream_path = Path("logs/federation_stream.jsonl")
    fed_state: dict[str, float] = {}
    fed_active_start: float | None = None
    if fed_stream_path.exists():
        for line in fed_stream_path.read_text().splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            did = ev.get("dialogue_id")
            if ev.get("event") == "start" and did:
                fed_state[did] = ev.get("ts", 0.0)
            elif ev.get("event") == "end" and did in fed_state:
                fed_state.pop(did, None)
        if fed_state:
            fed_active_start = sorted(fed_state.values())[0]
    if fed_active_start is not None:
        fed_elapsed = int(time.time() - fed_active_start)
        sidebar.write(f"Federated Active Now ({fed_elapsed}s)")

    fed_path = Path("logs/federation_log.jsonl")
    if fed_path.exists():
        lines = fed_path.read_text().splitlines()
        if lines:
            sidebar.subheader("Federated Presence")
            for line in lines[-5:][::-1]:
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                ts = entry.get("end_ts") or entry.get("start_ts")
                ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "unknown"
                agents = ", ".join(entry.get("agents", []))
                src = entry.get("source", "unknown")
                sidebar.write(f"[{src}] {entry.get('dialogue_id')} ({agents}) {ts_str}")

    if page == "WDM":
        wdm_panel.render()
        return
    if page == "Forge":
        _render_forge_panel()
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


def _render_forge_panel() -> None:
    if st is None:
        return
    repo_root = Path.cwd()
    status = compute_status(repo_root)
    index = rebuild_index(repo_root)
    policy = _load_policy(repo_root / "glow/forge/policy.json")
    raw_allowed = policy.get("allowlisted_goal_ids")
    allowed_goals = [item for item in raw_allowed if isinstance(item, str)] if isinstance(raw_allowed, list) else []
    queue = ForgeQueue(pulse_root=repo_root / "pulse")
    sentinel = ContractSentinel(repo_root=repo_root, queue=queue)

    st.title("Forge Observatory")
    st.subheader("Live Status")
    st.json(status.to_dict())

    st.subheader("Contract Sentinel")
    sentinel_status = sentinel.summary()
    st.json(sentinel_status)
    scol1, scol2, scol3 = st.columns(3)
    with scol1:
        if st.button("Sentinel enable"):
            policy = sentinel.load_policy()
            policy.enabled = True
            sentinel.save_policy(policy)
            st.success("Sentinel enabled")
    with scol2:
        if st.button("Sentinel disable"):
            policy = sentinel.load_policy()
            policy.enabled = False
            sentinel.save_policy(policy)
            st.success("Sentinel disabled")
    with scol3:
        if st.button("Run Sentinel tick now"):
            result = sentinel.tick()
            st.json(result)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Run daemon tick now"):
            result = subprocess.run([sys.executable, "-m", "sentientos.forge", "run-daemon-tick"], capture_output=True, text=True, check=False)
            st.code(result.stdout or result.stderr)
    with col2:
        if st.button("Rebuild index"):
            refreshed = rebuild_index(repo_root)
            st.success(f"index generated at {refreshed.get('generated_at')}")

    st.subheader("Queue (pending)")
    st.dataframe(index.get("latest_queue", []))
    st.subheader("Receipts (latest)")
    st.dataframe(index.get("latest_receipts", []))

    st.subheader("Quarantines")
    quarantines = index.get("latest_quarantines", [])
    st.dataframe(quarantines)
    if isinstance(quarantines, list) and quarantines:
        selected = st.selectbox("Quarantine", [str(item.get("path", "")) for item in quarantines])
        if selected:
            st.code(selected)
            st.json(next((item for item in quarantines if str(item.get("path", "")) == selected), {}))

    if allowed_goals:
        st.subheader("Enqueue allowlisted goal")
        selected_goal = st.selectbox("Goal", allowed_goals)
        if st.button("Enqueue goal"):
            request_id = queue.enqueue(ForgeRequest(request_id="", goal=selected_goal, goal_id=selected_goal, requested_by="cathedral_gui"))
            st.success(f"Queued {request_id}")
    else:
        st.info("No allowlisted goals configured in glow/forge/policy.json")


    st.subheader("Provenance")
    provenance_rows = index.get("latest_provenance", [])
    st.dataframe(provenance_rows)
    chain_payload = index.get("provenance_chain", {})
    st.json(chain_payload)
    pcol1, pcol2 = st.columns(2)
    with pcol1:
        selected_prov = st.selectbox("Provenance bundle", [str(item.get("path", "")) for item in provenance_rows] if isinstance(provenance_rows, list) and provenance_rows else [""])
        if selected_prov:
            st.code(selected_prov)
    with pcol2:
        if st.button("Validate provenance chain"):
            refreshed = rebuild_index(repo_root)
            st.json(refreshed.get("provenance_chain", {}))
    replay_target = st.text_input("Replay target (run_id or provenance path)", value="")
    replay_dry_run = st.checkbox("Replay dry-run", value=True)
    if st.button("Replay") and replay_target.strip():
        result = subprocess.run([sys.executable, "-m", "sentientos.forge", "replay", replay_target.strip(), *( ["--dry-run"] if replay_dry_run else [] )], capture_output=True, text=True, check=False)
        st.code(result.stdout or result.stderr)

    st.subheader("Latest report")
    reports = index.get("latest_reports", [])
    st.json(reports[-1] if isinstance(reports, list) and reports else {})
    st.subheader("Latest docket")
    dockets = index.get("latest_dockets", [])
    st.json(dockets[-1] if isinstance(dockets, list) and dockets else {})


def forge_panel_registered() -> bool:
    """Smoke-test helper used by unit tests."""

    return True


if __name__ == "__main__":  # pragma: no cover - manual
    main()
