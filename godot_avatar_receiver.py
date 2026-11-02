"""Forward avatar state JSON updates to Godot via UDP."""
from __future__ import annotations

import argparse
import json
import math
import re
import socket
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from sentientos.storage import get_state_file

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18188
DEFAULT_INTERVAL = 0.25
MAX_STATE_FILE_BYTES = 64 * 1024
MAX_UDP_PAYLOAD_BYTES = 60 * 1024
MAX_VISEME_CUES = 256
MAX_PHRASE_CHARS = 2048
_OUTPUT_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_CORRELATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


def _finite_number(value: object, default: float) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


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
            with self.state_path.open("rb") as source:
                encoded = source.read(MAX_STATE_FILE_BYTES + 1)
            if len(encoded) > MAX_STATE_FILE_BYTES:
                return None
            raw = json.loads(encoded.decode("utf-8"))
        except FileNotFoundError:
            return None
        except OSError:
            return None
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
            return None
        if not isinstance(raw, dict):
            return None

        intensity_value = _finite_number(raw.get("intensity", 0.0), 0.0)
        if intensity_value is None:
            return None
        intensity = max(0.0, min(1.0, intensity_value))

        phrase_value = raw.get("phrase")
        phrase_data: dict[str, Any] = phrase_value if isinstance(phrase_value, dict) else {}
        phrase_text = phrase_data.get("text", raw.get("current_phrase", ""))
        if not isinstance(phrase_text, str) or len(phrase_text) > MAX_PHRASE_CHARS:
            return None
        started_value = phrase_data.get("started_at") if isinstance(phrase_data, dict) else None
        started_at = _finite_number(started_value, 0.0) if started_value is not None else None
        timestamp_value = _finite_number(raw.get("timestamp", time.time()), time.time())
        if timestamp_value is None or (started_value is not None and started_at is None):
            return None

        visemes = raw.get("viseme_timeline", raw.get("viseme_events", []))
        if visemes is None:
            visemes = []
        if not isinstance(visemes, list) or len(visemes) > MAX_VISEME_CUES:
            return None
        normalized_visemes: list[dict[str, object]] = []
        for cue in visemes:
            if not isinstance(cue, dict):
                return None
            cue_time = _finite_number(cue.get("time", 0.0), 0.0)
            duration = _finite_number(cue.get("duration", 0.05), 0.05)
            viseme = cue.get("viseme", cue.get("value", "neutral"))
            if (cue_time is None or duration is None or not isinstance(viseme, str)
                    or len(viseme) > 32):
                return None
            normalized_visemes.append({
                "time": cue_time,
                "duration": max(0.0, duration),
                "viseme": viseme,
            })

        labels = {key: raw.get(key) for key in ("mood", "expression", "motion")}
        if any(not isinstance(value, str) or not value or len(value) > 128
               for value in labels.values()):
            return None

        payload: Dict[str, Any] = {
            "mode": raw.get("mode") if isinstance(raw.get("mode"), str) else None,
            "local_owner": bool(raw.get("local_owner", False)),
            "mood": labels["mood"],
            "intensity": intensity,
            "expression": labels["expression"],
            "motion": labels["motion"],
            "current_phrase": phrase_text,
            "phrase": {
                "text": phrase_text,
                "started_at": started_at,
                "muted": bool(phrase_data.get("muted", raw.get("muted", False))),
                "viseme_count": phrase_data.get("viseme_count", 0),
                "speaking": bool(phrase_data.get("speaking", raw.get("speaking", raw.get("is_speaking", False)))),
            },
            "is_speaking": bool(raw.get("is_speaking", False)),
            "speaking": bool(raw.get("speaking", raw.get("is_speaking", False))),
            "viseme_timeline": normalized_visemes,
            "timestamp": timestamp_value,
        }
        metadata = raw.get("metadata")
        workload_mode = metadata.get("workload_mode") if isinstance(metadata, dict) else None
        if isinstance(workload_mode, str) and workload_mode in {"normal", "gaming"}:
            payload["workload_mode"] = workload_mode
        if isinstance(metadata, dict):
            correlation: Dict[str, str] = {}
            for field in ("session_id", "turn_id"):
                value = metadata.get(field)
                if isinstance(value, str) and _CORRELATION_ID.fullmatch(value):
                    correlation[field] = value
            output_digest = metadata.get("output_digest")
            output_mode = metadata.get("output_mode")
            if (len(correlation) == 2 and isinstance(output_digest, str)
                    and _OUTPUT_DIGEST.fullmatch(output_digest)
                    and output_mode == "chat_response_visual_only"):
                payload["metadata"] = {**correlation,
                    "output_digest": output_digest, "output_mode": output_mode}
        if not all(payload.get(key) for key in ("mood", "expression", "motion")):
            return None
        if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_UDP_PAYLOAD_BYTES:
            return None
        return payload

    def _send(self, sock: socket.socket, payload: Dict[str, Any]) -> None:
        message = json.dumps(payload).encode("utf-8")
        sock.sendto(message, (self.host, self.port))
        mood = payload.get("mood")
        expression = payload.get("expression")
        motion = payload.get("motion")
        intensity = payload.get("intensity")
        phrase_value = payload.get("phrase")
        phrase_info: dict[str, Any] = phrase_value if isinstance(phrase_value, dict) else {}
        phrase = phrase_info.get("text") or payload.get("current_phrase")
        speaking = payload.get("speaking")
        status = ""
        if phrase:
            status = f" phrase='{phrase}'"
            if phrase_info.get("muted"):
                status += " [muted]"
        print(
            "[avatar-forwarder] mood={mood} expression={expression} motion={motion} intensity={intensity}" + status
        )


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
    return Path(get_state_file("avatar_state.json"))


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
