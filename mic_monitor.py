"""Real-time loudness monitoring for SentientOS."""
from __future__ import annotations

import importlib
import importlib.util
import json
import math
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Deque, List, Optional

from logging_config import get_log_path
from perception_journal import PerceptionJournal

_np_spec = importlib.util.find_spec("numpy")
np = importlib.import_module("numpy") if _np_spec is not None else None

_sounddevice_spec = importlib.util.find_spec("sounddevice")
sounddevice = importlib.import_module("sounddevice") if _sounddevice_spec is not None else None


@dataclass
class MicEvent:
    """High-level description of a loudness event."""

    start: datetime
    end: datetime
    peak_db: float
    average_db: float
    samples: int
    tags: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return (self.end - self.start).total_seconds()


class MicMonitor:
    """Monitor microphone RMS levels and log threshold crossings."""

    def __init__(
        self,
        threshold_db: float = 70.0,
        min_duration: float = 1.5,
        sample_rate: int = 16_000,
        window_seconds: float = 0.5,
        log_path: Path | None = None,
        journal: Optional[PerceptionJournal] = None,
    ) -> None:
        if threshold_db <= 0:
            raise ValueError("threshold_db must be positive")
        if min_duration <= 0:
            raise ValueError("min_duration must be positive")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.threshold_db = threshold_db
        self.min_duration = min_duration
        self.sample_rate = sample_rate
        self.window_seconds = window_seconds
        self.log_path = log_path or get_log_path("loudness.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.journal = journal or PerceptionJournal()
        self._events: Deque[MicEvent] = deque(maxlen=512)
        self._lock = threading.Lock()
        self._current_event: MicEvent | None = None
        self._current_levels: List[float] = []
        self._last_state = "quiet"
        self._last_above: datetime | None = None
        self._stream: Optional[object] = None
        self._stop = threading.Event()

    def _handle_level(self, level_db: float, timestamp: datetime) -> MicEvent | None:
        if self._current_event is None and level_db >= self.threshold_db:
            self._current_event = MicEvent(
                start=timestamp,
                end=timestamp,
                peak_db=level_db,
                average_db=level_db,
                samples=1,
                tags=["noisy", "audio"],
            )
            self._current_levels = [level_db]
            self._last_above = timestamp
            if self._last_state != "noisy":
                self.journal.record(["noisy", "audio"], "Sustained loudness detected", {"level_db": level_db})
                self._last_state = "noisy"
            return None

        if self._current_event is not None:
            self._current_event.end = timestamp
            self._current_event.peak_db = max(self._current_event.peak_db, level_db)
            self._current_levels.append(level_db)
            self._current_event.samples += 1
            self._current_event.average_db = float(sum(self._current_levels) / len(self._current_levels))
            if level_db >= self.threshold_db:
                self._last_above = timestamp
                return None
            if self._last_above is None:
                self._last_above = self._current_event.start
            if timestamp - self._last_above >= timedelta(seconds=self.window_seconds):
                if self._current_event.duration >= self.min_duration:
                    self._finalize_event(self._current_event)
                    finished = self._current_event
                else:
                    finished = None
                self._current_event = None
                self._current_levels = []
                self._last_above = None
                if self._last_state != "quiet":
                    self.journal.record(["quiet", "audio"], "Noise levels returned to baseline")
                    self._last_state = "quiet"
                return finished
            return None

        if self._last_state != "quiet":
            self.journal.record(["quiet", "audio"], "Ambient levels nominal")
            self._last_state = "quiet"
        return None

    def _finalize_event(self, event: MicEvent) -> None:
        payload = {
            "start": event.start.isoformat(),
            "end": event.end.isoformat(),
            "peak_db": round(event.peak_db, 2),
            "average_db": round(event.average_db, 2),
            "duration": round(event.duration, 2),
            "tags": event.tags,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
        with self._lock:
            self._events.append(event)

    def process_block(self, samples: np.ndarray, sample_rate: Optional[int] = None, timestamp: Optional[datetime] = None) -> MicEvent | None:
        """Process a manual block of audio samples."""

        if np is not None:
            arr = np.asarray(samples, dtype=np.float64)
            if arr.ndim > 1:
                arr = arr.mean(axis=1)
            rms = float(np.sqrt(np.mean(np.square(arr))))
        else:
            if not samples:
                rms = 0.0
            else:
                if isinstance(samples[0], (list, tuple)):
                    flattened = [sum(map(float, row)) / len(row) for row in samples]  # type: ignore[arg-type]
                else:
                    flattened = [float(x) for x in samples]
                total = sum(val * val for val in flattened)
                rms = math.sqrt(total / len(flattened))
        rms = max(rms, 1e-12)
        db = 20 * math.log10(rms) + 94.0
        ts = timestamp or datetime.utcnow()
        return self._handle_level(db, ts)

    def start(self, device: Optional[int] = None) -> None:  # pragma: no cover - requires hardware
        if sounddevice is None:
            print("[MIC_MONITOR] sounddevice not available; skipping live monitor")
            return
        blocksize = max(1, int(self.sample_rate * self.window_seconds))

        def _callback(indata: np.ndarray, _: int, __: int, ___: int) -> None:
            self.process_block(indata[:, 0], sample_rate=self.sample_rate)

        self._stop.clear()
        self._stream = sounddevice.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            device=device,
            callback=_callback,
            blocksize=blocksize,
        )
        self._stream.start()

    def stop(self) -> None:  # pragma: no cover - requires hardware
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._stop.set()

    def recent_events(self, window: float = 300.0) -> List[MicEvent]:
        cutoff = datetime.utcnow() - timedelta(seconds=window)
        with self._lock:
            return [ev for ev in list(self._events) if ev.end >= cutoff]

    def events_between(self, start: datetime, end: datetime) -> List[MicEvent]:
        with self._lock:
            return [ev for ev in self._events if ev.start <= end and ev.end >= start]


__all__ = ["MicMonitor", "MicEvent"]
