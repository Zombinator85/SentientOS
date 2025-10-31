"""Camera daemon for SentientOS vision monitoring."""
from __future__ import annotations

import importlib
import importlib.util
import json
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Deque, Iterable, Iterator, List, Optional, TYPE_CHECKING

_np_spec = importlib.util.find_spec("numpy")
np = importlib.import_module("numpy") if _np_spec is not None else None

from audit_chain import append_entry
from logging_config import get_log_path
from motion_detector import MotionDetectionResult, MotionDetector
from perception_journal import PerceptionJournal

if TYPE_CHECKING:
    from mic_monitor import MicMonitor
    from reporter import IncidentReporter

_cv2_spec = importlib.util.find_spec("cv2")
cv2 = importlib.import_module("cv2") if _cv2_spec is not None else None


@dataclass
class FrameRecord:
    timestamp: datetime
    frame: object


@dataclass
class CameraEvent:
    event_id: str
    start: datetime
    end: datetime
    clip_path: Path
    peak_score: float
    frame_count: int
    bundle: Optional[Path] = None


class ClipWriter:
    """Write captured frames to a local clip file."""

    def __init__(self, path: Path, fps: int, resolution: tuple[int, int]) -> None:
        self.path = path
        self.fps = fps
        self.resolution = resolution
        self._frames: List[object] = []
        self._writer: Optional[object] = None
        if cv2 is not None and path.suffix.lower() not in {".npz", ".json"}:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self._writer = cv2.VideoWriter(str(path), fourcc, fps, resolution)
        else:
            suffix = ".npz" if np is not None else ".json"
            self.path = path.with_suffix(suffix)

    def write(self, frame: object) -> None:
        if self._writer is not None:
            self._writer.write(frame)
            return
        if np is not None:
            self._frames.append(np.asarray(frame))
        elif isinstance(frame, list):
            self._frames.append(json.loads(json.dumps(frame)))
        else:
            self._frames.append(frame)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.release()
            return
        if self._frames:
            if np is not None:
                np.savez_compressed(self.path, frames=np.array(self._frames))
            else:
                with self.path.open("w", encoding="utf-8") as handle:
                    json.dump(self._frames, handle)


class CameraDaemon:
    """Background camera daemon performing motion detection and recording."""

    def __init__(
        self,
        source: int | str | None = 0,
        fps: int = 15,
        resolution: tuple[int, int] = (1280, 720),
        frame_skip: int = 1,
        pre_event_seconds: int = 30,
        post_event_seconds: int = 30,
        trigger_score: float = 0.05,
        log_dir: Path | None = None,
        detector: Optional[MotionDetector] = None,
        journal: Optional[PerceptionJournal] = None,
        mic_monitor: Optional["MicMonitor"] = None,
        reporter: Optional["IncidentReporter"] = None,
        frame_provider: Optional[Iterator[FrameRecord]] = None,
    ) -> None:
        if fps <= 0:
            raise ValueError("fps must be positive")
        if frame_skip <= 0:
            raise ValueError("frame_skip must be positive")
        if pre_event_seconds < 0 or post_event_seconds < 0:
            raise ValueError("event windows must be non-negative")
        if trigger_score <= 0:
            raise ValueError("trigger_score must be positive")
        self.source = source
        self.fps = fps
        self.frame_skip = frame_skip
        self.resolution = resolution
        self.pre_event_seconds = pre_event_seconds
        self.post_event_seconds = post_event_seconds
        self.trigger_score = trigger_score
        self.log_root = log_dir or get_log_path("camera")
        self.log_root.mkdir(parents=True, exist_ok=True)
        self.events_log = self.log_root / "events.jsonl"
        self.clips_dir = self.log_root / "clips"
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log = get_log_path("camera_audit.jsonl")
        self.detector = detector or MotionDetector()
        self.journal = journal or PerceptionJournal()
        self.mic_monitor = mic_monitor
        self.reporter = reporter
        self.frame_provider = frame_provider
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._buffer: Deque[FrameRecord] = deque(maxlen=max(1, fps * pre_event_seconds))
        self._active_frames: List[FrameRecord] = []
        self._active_peak = 0.0
        self._active_start: Optional[datetime] = None
        self._last_motion: Optional[datetime] = None
        self._last_state = "quiet"
        self._events: Deque[CameraEvent] = deque(maxlen=64)

    def _camera_frames(self) -> Iterator[FrameRecord]:  # pragma: no cover - requires hardware
        if cv2 is None or self.source is None:
            raise RuntimeError("OpenCV not available for live capture")
        cap = cv2.VideoCapture(self.source)
        if self.resolution:
            width, height = self.resolution
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        skip_counter = 0
        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.1)
                continue
            if skip_counter % self.frame_skip == 0:
                yield FrameRecord(timestamp=datetime.utcnow(), frame=frame)
            skip_counter += 1
        cap.release()

    def start(self) -> None:  # pragma: no cover - requires hardware
        if self._thread and self._thread.is_alive():
            return
        def _loop() -> None:
            provider = self.frame_provider or self._camera_frames()
            self.process_stream(provider)
        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:  # pragma: no cover - requires hardware
        self._stop.set()
        if self._thread:
            self._thread.join()

    def process_stream(self, frames: Iterable[FrameRecord]) -> None:
        for record in frames:
            self._buffer.append(record)
            detection = self.detector.update(record.frame, timestamp=record.timestamp)
            if detection:
                if detection.score < self.trigger_score:
                    self._handle_idle(record.timestamp)
                else:
                    self._handle_motion(record, detection)
            else:
                self._handle_idle(record.timestamp)

    def _handle_motion(self, record: FrameRecord, detection: MotionDetectionResult) -> None:
        if self._last_state != "motion":
            self.journal.record(["motion_detected", "vision"], "Camera observed motion", {"score": detection.score})
            self._last_state = "motion"
        if self._active_start is None:
            self._active_start = record.timestamp
            self._active_frames = list(self._buffer)
        self._active_frames.append(record)
        self._last_motion = record.timestamp
        self._active_peak = max(self._active_peak, detection.score)

    def _handle_idle(self, timestamp: datetime) -> None:
        if self._active_start is None:
            if self._last_state != "quiet":
                self.journal.record(["quiet", "vision"], "Scene calm")
                self._last_state = "quiet"
            return
        assert self._last_motion is not None
        if timestamp - self._last_motion < timedelta(seconds=self.post_event_seconds):
            self._active_frames.append(FrameRecord(timestamp=timestamp, frame=self._active_frames[-1].frame))
            return
        self._finalize_event(timestamp)

    def _finalize_event(self, timestamp: datetime) -> None:
        assert self._active_start is not None
        start = self._active_start
        end = timestamp
        event_id = uuid.uuid4().hex
        if cv2 is not None:
            clip_name = f"{event_id}.mp4"
        else:
            ext = ".npz" if np is not None else ".json"
            clip_name = f"{event_id}{ext}"
        clip_path = self.clips_dir / clip_name
        writer = ClipWriter(clip_path, self.fps, self.resolution)
        for item in self._active_frames:
            writer.write(item.frame)
        writer.close()
        summary = {
            "event_id": event_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "clip_path": str(writer.path if hasattr(writer, "path") else clip_path),
            "peak_score": round(self._active_peak, 4),
            "frame_count": len(self._active_frames),
        }
        with self.events_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(summary) + "\n")
        append_entry(self.audit_log, {"type": "camera_event", "event": summary})
        bundle_path: Optional[Path] = None
        if self.reporter is not None:
            from reporter import IncidentReporter, IncidentSummary  # local import to avoid cycle

            assert isinstance(self.reporter, IncidentReporter)
            mic_events: List[dict[str, object]] = []
            if self.mic_monitor is not None:
                mic_events = [
                    {
                        "start": ev.start.isoformat(),
                        "end": ev.end.isoformat(),
                        "peak_db": round(ev.peak_db, 2),
                        "average_db": round(ev.average_db, 2),
                        "duration": round(ev.duration, 2),
                        "tags": ev.tags,
                    }
                    for ev in self.mic_monitor.events_between(
                        start - timedelta(seconds=self.pre_event_seconds),
                        end + timedelta(seconds=self.post_event_seconds),
                    )
                ]
            bundle_path = self.reporter.build_bundle(
                IncidentSummary(
                    event_id=event_id,
                    start=start,
                    end=end,
                    clip_path=Path(summary["clip_path"]),
                    peak_score=self._active_peak,
                ),
                mic_events,
            )
            if bundle_path is not None:
                summary["bundle_path"] = str(bundle_path)
        event = CameraEvent(
            event_id=event_id,
            start=start,
            end=end,
            clip_path=Path(summary["clip_path"]),
            peak_score=self._active_peak,
            frame_count=len(self._active_frames),
            bundle=bundle_path,
        )
        self._events.append(event)
        self._active_start = None
        self._active_frames = []
        self._active_peak = 0.0
        self._last_motion = None
        self.journal.record(["quiet", "vision"], "Motion event resolved")
        self._last_state = "quiet"

    def recent_events(self, window: float = 600.0) -> List[CameraEvent]:
        cutoff = datetime.utcnow() - timedelta(seconds=window)
        return [ev for ev in list(self._events) if ev.end >= cutoff]


__all__ = ["CameraDaemon", "CameraEvent", "FrameRecord"]
