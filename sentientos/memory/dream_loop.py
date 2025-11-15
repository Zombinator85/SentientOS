"""Deterministic Dream Loop implementation."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

from .glow import GlowShard, build_glow_shard, count_glow_shards, save_glow_shard
from .mounts import MemoryMounts
from .pulse_view import collect_recent_pulse

LogCallback = Callable[[str, Optional[Dict[str, object]]], None]


class DreamLoop:
    """Periodic background loop that writes deterministic glow shards."""

    def __init__(
        self,
        runtime,
        mounts: MemoryMounts,
        interval_seconds: int,
        log_cb: LogCallback,
        *,
        max_recent_shards: int = 5,
    ) -> None:
        self.runtime = runtime
        self.mounts = mounts
        self.interval_seconds = max(5, int(interval_seconds))
        self.log_cb = log_cb
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_ts: Optional[datetime] = None
        self._lock = threading.Lock()
        self._last_shard: Optional[GlowShard] = None
        self._max_recent = max(1, int(max_recent_shards))
        self._journal_path = Path(mounts.glow) / "glow_journal.jsonl"
        self._shard_count = count_glow_shards(mounts)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if self._last_ts is None:
            self._last_ts = datetime.now(timezone.utc) - timedelta(minutes=5)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="DreamLoop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is None:
            return
        thread.join(timeout=self.interval_seconds * 2)
        self._thread = None

    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    def run_once(self) -> bool:
        cutoff = self._last_ts or (datetime.now(timezone.utc) - timedelta(minutes=5))
        try:
            pulses = collect_recent_pulse(self.runtime, cutoff)
        except Exception as exc:  # pragma: no cover - defensive
            self.log_cb(
                "DreamLoop: pulse collection failed",
                {"error": str(exc)},
            )
            self._advance_cutoff()
            return False
        if not pulses:
            self._advance_cutoff()
            return False
        shard = build_glow_shard(pulses)
        try:
            save_glow_shard(self.mounts, shard, max_recent=self._max_recent)
        except Exception as exc:  # pragma: no cover - defensive
            self.log_cb(
                "DreamLoop: failed to persist shard",
                {"id": shard.id, "error": str(exc)},
            )
            with self._lock:
                self._last_ts = shard.created_at
            return False
        with self._lock:
            self._last_ts = max((event.ts for event in pulses), default=shard.created_at)
            self._last_shard = shard
            self._shard_count += 1
        self.log_cb(
            "DreamLoop: wrote shard",
            {"id": shard.id, "focus": shard.focus, "pulses": len(shard.pulses)},
        )
        return True

    def status(self) -> Dict[str, object]:
        with self._lock:
            shard = self._last_shard
            count = self._shard_count
        if shard is None:
            if self._journal_path.exists():
                count = count_glow_shards(self.mounts)
            last_focus = None
            last_summary = None
            last_id = None
            last_created_at = None
        else:
            entry = shard
            last_focus = shard.focus
            last_summary = shard.summary
            last_id = shard.id
            last_created_at = shard.created_at
        return {
            "running": self.is_running(),
            "last_shard_id": last_id,
            "last_focus": last_focus,
            "last_summary": last_summary,
            "last_created_at": last_created_at,
            "shard_count": count,
        }

    def _advance_cutoff(self) -> None:
        with self._lock:
            self._last_ts = datetime.now(timezone.utc)

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            if self._stop.wait(self.interval_seconds):
                break
