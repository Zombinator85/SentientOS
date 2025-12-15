"""Forward avatar state JSON updates to Godot via UDP."""
from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from sentientos.storage import get_state_file

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18188
DEFAULT_INTERVAL = 0.25


class AvatarStateForwarder:
    """Watch ``avatar_state.json`` and send updates to a Godot listener."""

    def __init__(
        self,
        state_path: Path,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        poll_interval: float = DEFAULT_INTERVAL,
    ) -> None:
        self.state_path = state_path
        self.host = host
        self.port = port
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_token: Optional[str] = None

    def start(self) -> None:
        """Start forwarding in a background thread."""

        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.run, name="avatar-forwarder", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop forwarding and wait briefly for the loop to exit."""

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def run(self) -> None:
        """Blocking loop for forwarding state changes."""

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            while not self._stop_event.is_set():
                payload = self._read_state()
                if payload:
                    token = payload.get("timestamp") or json.dumps(payload, sort_keys=True)
                    if token != self._last_token:
                        self._send(sock, payload)
                        self._last_token = token
                self._stop_event.wait(self.poll_interval)

    def _read_state(self) -> Optional[Dict[str, Any]]:
        try:
            raw = json.loads(self.state_path.read_text())
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            return None

        try:
            intensity = float(raw.get("intensity", 0.0))
        except (TypeError, ValueError):
            intensity = 0.0

        payload: Dict[str, Any] = {
            "mode": raw.get("mode"),
            "local_owner": bool(raw.get("local_owner", False)),
            "mood": raw.get("mood"),
            "intensity": intensity,
            "expression": raw.get("expression"),
            "motion": raw.get("motion"),
            "timestamp": raw.get("timestamp", time.time()),
        }
        metadata = raw.get("metadata")
        if isinstance(metadata, dict):
            payload["metadata"] = metadata

        if not all(payload.get(key) for key in ("mood", "expression", "motion")):
            return None
        return payload

    def _send(self, sock: socket.socket, payload: Dict[str, Any]) -> None:
        message = json.dumps(payload).encode("utf-8")
        sock.sendto(message, (self.host, self.port))
        mood = payload.get("mood")
        expression = payload.get("expression")
        motion = payload.get("motion")
        intensity = payload.get("intensity")
        print(f"[avatar-forwarder] mood={mood} expression={expression} motion={motion} intensity={intensity}")


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send avatar_state.json updates to Godot over UDP")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Godot listener host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Godot listener port")
    parser.add_argument(
        "--state-file",
        type=Path,
        default=None,
        help="Override avatar_state.json path (defaults to SENTIENTOS_DATA_DIR/avatar_state.json)",
    )
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="Polling interval in seconds")
    return parser.parse_args(argv)


def _resolve_state_file(candidate: Optional[Path]) -> Path:
    if candidate:
        return candidate
    return get_state_file("avatar_state.json")


def main(argv: Optional[list[str]] = None) -> None:
    args = _parse_args(argv)
    forwarder = AvatarStateForwarder(
        _resolve_state_file(args.state_file), host=args.host, port=args.port, poll_interval=args.interval
    )
    try:
        forwarder.run()
    except KeyboardInterrupt:
        forwarder.stop()


if __name__ == "__main__":  # pragma: no cover - CLI tool
    main()
