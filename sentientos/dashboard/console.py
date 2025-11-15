"""Text-based console dashboard rendering for SentientOS."""

from __future__ import annotations

import io
import sys
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Sequence

__all__ = [
    "DashboardStatus",
    "LogBuffer",
    "ConsoleDashboard",
]


@dataclass
class DashboardStatus:
    """Snapshot of runtime state displayed by the dashboard."""

    node_name: str
    model_name: str
    model_status: str
    persona_enabled: bool
    persona_mood: Optional[str]
    last_persona_msg: Optional[str]
    experiments_run: int
    experiments_success: int
    experiments_failed: int
    last_experiment_desc: Optional[str]
    last_experiment_result: Optional[str]
    consensus_mode: str
    last_update_ts: datetime
    cathedral_accepted: int = 0
    cathedral_applied: int = 0
    cathedral_quarantined: int = 0
    cathedral_rollbacks: int = 0
    cathedral_auto_reverts: int = 0
    last_applied_id: Optional[str] = None
    last_quarantined_id: Optional[str] = None
    last_quarantine_error: Optional[str] = None
    last_reverted_id: Optional[str] = None
    federation_enabled: bool = False
    federation_node: Optional[str] = None
    federation_fingerprint: Optional[str] = None
    federation_peer_total: int = 0
    federation_healthy: int = 0
    federation_drift: int = 0
    federation_incompatible: int = 0
    federation_peers: Dict[str, str] = field(default_factory=dict)


class LogBuffer:
    """In-memory ring buffer that preserves recent log lines."""

    def __init__(self, max_lines: int = 50) -> None:
        if max_lines <= 0:
            raise ValueError("max_lines must be positive")
        self._entries: deque[str] = deque(maxlen=max_lines)
        self._pending: deque[str] = deque()
        self._lock = threading.Lock()
        self._max_lines = max_lines

    @property
    def max_lines(self) -> int:
        return self._max_lines

    def add(self, line: str) -> None:
        """Append a formatted line to the buffer with timestamp."""

        text = line.rstrip()
        if not text:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        if not text.lstrip().startswith("["):
            text = f"[{timestamp}] {text}"
        with self._lock:
            self._entries.append(text)
            self._pending.append(text)

    def extend(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.add(str(line))

    def get_recent(self, limit: Optional[int] = None) -> List[str]:
        """Return the most recent log lines, newest last."""

        with self._lock:
            if limit is None:
                return list(self._entries)
            if limit <= 0:
                return []
            return list(self._entries)[-limit:]

    def consume_pending(self) -> List[str]:
        """Return newly added lines since the last call."""

        with self._lock:
            items = list(self._pending)
            self._pending.clear()
        return items


class ConsoleDashboard:
    """Simple console renderer for runtime and demo status."""

    def __init__(
        self,
        status_source: Callable[[], DashboardStatus],
        log_stream_source: Optional[Callable[[], Sequence[str]]] = None,
        refresh_interval: float = 2.0,
        *,
        log_buffer: Optional[LogBuffer] = None,
        output_stream: Optional[io.TextIOBase] = None,
        recent_event_limit: int = 10,
    ) -> None:
        if refresh_interval <= 0:
            raise ValueError("refresh_interval must be positive")
        self._status_source = status_source
        self._log_stream_source = log_stream_source
        self._refresh_interval = float(refresh_interval)
        self._stop_event = threading.Event()
        self._log_buffer = log_buffer or LogBuffer()
        self._recent_event_limit = max(1, int(recent_event_limit))
        self._output = output_stream or sys.stdout
        owner = getattr(log_stream_source, "__self__", None)
        if owner is None and log_stream_source is not None:
            owner = getattr(log_stream_source, "_log_buffer", None)
        self._log_source_owner = owner

    @property
    def log_buffer(self) -> LogBuffer:
        return self._log_buffer

    def stop(self) -> None:
        """Request termination of the dashboard loop."""

        self._stop_event.set()

    def run_once(self) -> str:
        """Render a single frame to the configured output stream."""

        status = self._status_source()
        if self._log_stream_source:
            try:
                new_lines = self._log_stream_source()
            except Exception:
                new_lines = []
            else:
                if new_lines is None:
                    new_lines = []
            for line in new_lines:
                if self._log_source_owner is self._log_buffer:
                    # Already recorded in buffer via consume_pending().
                    continue
                self._log_buffer.add(str(line))

        frame = self._render(status)
        if not frame.endswith("\n"):
            frame += "\n"
        self._output.write(frame)
        self._output.flush()
        return frame

    def run_loop(self) -> None:
        """Continuously render dashboard frames until stopped."""

        try:
            while not self._stop_event.is_set():
                self.run_once()
                if self._stop_event.wait(self._refresh_interval):
                    break
        except KeyboardInterrupt:
            self.stop()
            raise

    def _render(self, status: DashboardStatus) -> str:
        header = "=" * 16 + " SentientOS Dashboard " + "=" * 16
        footer = "=" * len(header)

        model_status = status.model_status.upper()
        persona_line: str
        if status.persona_enabled:
            mood = status.persona_mood or "unknown"
            heartbeat = status.last_persona_msg or "(no heartbeat yet)"
            persona_line = (
                f"Persona: {'Lumos' if status.persona_mood else 'Persona'} (mood: {mood})  "
                f"Heartbeat: {heartbeat}"
            )
        else:
            persona_line = "Persona: disabled"

        last_experiment = "None recorded"
        if status.last_experiment_desc:
            outcome = status.last_experiment_result or "unknown"
            last_experiment = f"{status.last_experiment_desc} → {outcome.upper()}"

        experiments_line = (
            "Experiments: "
            f"{status.experiments_run} total  |  "
            f"{status.experiments_success} success, {status.experiments_failed} fail  |  "
            f"Last: {last_experiment}"
        )
        cathedral_line = (
            "Cathedral: "
            f"Accepted: {status.cathedral_accepted}  |  "
            f"Applied: {status.cathedral_applied}  |  "
            f"Rollbacks: {status.cathedral_rollbacks}  |  "
            f"Auto-Reverts: {status.cathedral_auto_reverts}"
        )
        if status.last_applied_id:
            cathedral_line += f"  |  Last Applied: {status.last_applied_id}"
        if status.last_reverted_id:
            cathedral_line += f"  |  Last Reverted: {status.last_reverted_id}"
        if status.last_quarantined_id:
            cathedral_line += f"  |  Last Quarantined: {status.last_quarantined_id}"
        if status.federation_enabled:
            fingerprint = status.federation_fingerprint or "n/a"
            node_label = status.federation_node or status.node_name
            federation_line = (
                "Federation: "
                f"Enabled  |  Node: {node_label} (fingerprint: {fingerprint})  |  "
                f"Peers: {status.federation_peer_total}  Healthy: {status.federation_healthy}  "
                f"Drift: {status.federation_drift}  Incompatible: {status.federation_incompatible}"
            )
        else:
            federation_line = "Federation: disabled"
        peer_lines: List[str] = []
        if status.federation_peers:
            for peer, level in list(status.federation_peers.items())[:3]:
                peer_lines.append(f"    {peer}: {level.upper()}")
        timestamp = status.last_update_ts.strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            header,
            (
                f"Node: {status.node_name:<14}  "
                f"Model: {status.model_name}  "
                f"Status: {model_status}"
            ),
            persona_line,
            experiments_line,
            cathedral_line,
            federation_line,
            f"Consensus: {status.consensus_mode}  |  Updated: {timestamp}",
            "",
            "Recent events:",
        ]

        lines.extend(peer_lines)

        recent = self._log_buffer.get_recent(self._recent_event_limit)
        if not recent:
            lines.append("  (no recent events)")
        else:
            for entry in recent:
                lines.append(f"  {entry}")

        lines.extend(
            [
                "",
                "(Press Ctrl+C to stop, or use the CLI for commands.)",
                footer,
            ]
        )
        return "\n".join(lines)
