"""Bounded Windows game frame-time and per-process resource observations.

The adapter is read-only. Frame-time data is accepted only from an explicitly
configured PresentMon CSV source; process counters are read through optional
psutil support. Unsupported platforms and missing providers are reported
explicitly instead of being replaced with fixture or zero values.
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
import platform
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

MAX_PRESENTMON_BYTES = 4 * 1024 * 1024
MAX_PRESENTMON_ROWS = 100_000
PROCESS_CPU_SAMPLE_INTERVAL_SECONDS = 0.1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class GamePerformanceObservationError(ValueError):
    """Invalid process identity or malformed frame-time input."""


@dataclass(frozen=True, slots=True)
class GamePerformanceObservation:
    schema_version: str
    status: str
    observed_at: str
    process_id_digest: str | None
    process_cpu_percent: float | None
    process_rss_bytes: int | None
    frame_time_source: str
    frame_time_sample_count: int
    frame_time_p50_ms: float | None
    frame_time_p95_ms: float | None
    frame_time_p99_ms: float | None
    hitch_count_over_50ms: int | None
    frame_time_digest: str | None
    unsupported_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PresentMonFrameTiming:
    """One process-filtered PresentMon frame with a machine-clock timestamp."""

    cpu_start_qpc_ms: float
    frame_interval_ms: float
    frame_interval_source: str
    present_interval_ms: float | None
    cpu_busy_ms: float | None
    gpu_busy_ms: float | None
    displayed_time_ms: float | None
    display_status: str


@dataclass(frozen=True, slots=True)
class PresentMonTimelineSummary:
    """Experiment summary using an explicitly selected frame-rate target."""

    frame_count: int
    frame_time_p50_ms: float
    frame_time_p95_ms: float
    frame_time_p99_ms: float
    frame_time_max_ms: float
    target_frame_interval_ms: float
    missed_deadline_count: int
    hitch_threshold_ms: float
    long_frame_count: int
    long_frame_cluster_count: int
    dropped_presentation_count: int | None


def summarize_frame_times_ms(values: Sequence[float]) -> tuple[float, float, float, int]:
    """Return nearest-rank p50/p95/p99 and >50 ms hitches for bounded samples."""
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= MAX_PRESENTMON_ROWS:
        raise GamePerformanceObservationError("frame_time_sample_count_invalid")
    samples: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise GamePerformanceObservationError("frame_time_sample_invalid")
        sample = float(value)
        if not math.isfinite(sample) or sample <= 0 or sample > 10_000:
            raise GamePerformanceObservationError("frame_time_sample_invalid")
        samples.append(sample)
    samples.sort()

    def percentile(rank: float) -> float:
        index = max(0, math.ceil(rank * len(samples)) - 1)
        return round(samples[index], 4)

    return percentile(0.50), percentile(0.95), percentile(0.99), sum(x > 50.0 for x in samples)


def _decode_presentmon_csv(raw: bytes) -> str:
    """Decode UTF-8 CSVs and BOM-marked UTF-16 output redirected on Windows."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw.decode("utf-16")
        raise


def parse_presentmon_csv(raw: bytes, *, process_id: int) -> tuple[tuple[float, ...], str]:
    """Parse displayed-frame pacing from bounded PresentMon output.

    Prefer display intervals. PresentMon 2.x calls the duration a frame was
    displayed ``DisplayedTime``; legacy and app-frame intervals are fallbacks.
    Executable names and paths are never retained.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_PRESENTMON_BYTES:
        raise GamePerformanceObservationError("presentmon_input_size_invalid")
    if type(process_id) is not int or process_id < 1:
        raise GamePerformanceObservationError("game_process_id_invalid")
    try:
        text = _decode_presentmon_csv(raw)
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = set(reader.fieldnames or ())
        if "ProcessID" not in headers:
            raise GamePerformanceObservationError("presentmon_columns_missing")
        frame_time_columns = tuple(column for column in (
            "MsBetweenDisplayChange", "DisplayedTime",
            "MsBetweenPresents", "FrameTime",
        ) if column in headers)
        if not frame_time_columns:
            raise GamePerformanceObservationError("presentmon_columns_missing")
        samples_by_column: dict[str, list[float]] = {
            column: [] for column in frame_time_columns
        }
        rows_seen = 0
        for row in reader:
            rows_seen += 1
            if rows_seen > MAX_PRESENTMON_ROWS:
                raise GamePerformanceObservationError("presentmon_row_count_exceeded")
            try:
                row_pid = int(row["ProcessID"] or "")
            except (TypeError, ValueError):
                continue
            if row_pid != process_id:
                continue
            for column in frame_time_columns:
                raw_sample = row.get(column)
                if raw_sample is None or raw_sample.strip().casefold() in {"", "na", "n/a"}:
                    continue
                try:
                    sample = float(raw_sample)
                except (TypeError, ValueError) as exc:
                    raise GamePerformanceObservationError(
                        "presentmon_frame_time_invalid"
                    ) from exc
                if not math.isfinite(sample) or sample <= 0 or sample > 10_000:
                    raise GamePerformanceObservationError("presentmon_frame_time_invalid")
                samples_by_column[column].append(sample)
    except UnicodeError as exc:
        raise GamePerformanceObservationError("presentmon_encoding_invalid") from exc
    times = next((samples_by_column[column] for column in frame_time_columns
                  if samples_by_column[column]), [])
    if not times:
        raise GamePerformanceObservationError("presentmon_process_samples_missing")
    return tuple(times), hashlib.sha256(raw).hexdigest()


def _optional_timeline_number(row: Mapping[str, str | None], column: str, *,
                              invalid_reason: str,
                              maximum: float = 10_000.0) -> float | None:
    raw = row.get(column)
    if raw is None or raw.strip().casefold() in {"", "na", "n/a"}:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise GamePerformanceObservationError(invalid_reason) from exc
    if not math.isfinite(value) or value < 0 or value > maximum:
        raise GamePerformanceObservationError(invalid_reason)
    return round(value, 4)


def parse_presentmon_timeline(
    raw: bytes, *, process_id: int
) -> tuple[tuple[PresentMonFrameTiming, ...], str]:
    """Keep bounded per-frame timing for experiments that need event correlation.

    Use PresentMon's qpc_time_ms option to populate CPUStartQPCTimeInMs.
    The operational observer remains summary-only; this separate result keeps
    the source clock and per-frame CPU/GPU/display values without process names.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_PRESENTMON_BYTES:
        raise GamePerformanceObservationError("presentmon_input_size_invalid")
    if type(process_id) is not int or process_id < 1:
        raise GamePerformanceObservationError("game_process_id_invalid")
    try:
        text = _decode_presentmon_csv(raw)
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = set(reader.fieldnames or ())
        qpc_column = next((column for column in (
            "CPUStartQPCTimeInMs", "CPUStartQPCTime",
        ) if column in headers), None)
        if "ProcessID" not in headers or qpc_column is None:
            raise GamePerformanceObservationError("presentmon_timeline_columns_missing")
        display_interval_column = next((column for column in (
            "MsBetweenDisplayChange", "DisplayedTime") if column in headers
        ), None)
        present_interval_column = (
            "MsBetweenPresents" if "MsBetweenPresents" in headers else None
        )
        frame_interval_column = "FrameTime" if "FrameTime" in headers else None
        if (display_interval_column is None and present_interval_column is None
                and frame_interval_column is None):
            raise GamePerformanceObservationError("presentmon_columns_missing")

        frames: list[PresentMonFrameTiming] = []
        rows_seen = 0
        for row in reader:
            rows_seen += 1
            if rows_seen > MAX_PRESENTMON_ROWS:
                raise GamePerformanceObservationError("presentmon_row_count_exceeded")
            try:
                row_pid = int(row["ProcessID"] or "")
            except (TypeError, ValueError):
                continue
            if row_pid != process_id:
                continue

            qpc_ms = _optional_timeline_number(
                row, qpc_column, invalid_reason="presentmon_timestamp_invalid",
                maximum=1_000_000_000_000_000.0,
            )
            if qpc_ms is None:
                raise GamePerformanceObservationError("presentmon_timestamp_invalid")
            display_interval = (
                _optional_timeline_number(
                    row, display_interval_column,
                    invalid_reason="presentmon_frame_time_invalid",
                ) if display_interval_column else None
            )
            present_interval = (
                _optional_timeline_number(
                    row, present_interval_column,
                    invalid_reason="presentmon_frame_time_invalid",
                ) if present_interval_column else None
            )
            displayed_time = (
                _optional_timeline_number(
                    row, "DisplayedTime", invalid_reason="presentmon_display_time_invalid",
                ) if "DisplayedTime" in headers else None
            )
            frame_interval = (
                _optional_timeline_number(
                    row, frame_interval_column,
                    invalid_reason="presentmon_frame_time_invalid",
                ) if frame_interval_column else None
            )
            interval_candidates = (
                (display_interval, display_interval_column),
                (present_interval, present_interval_column),
                (frame_interval, frame_interval_column),
            )
            interval, interval_source = next(
                ((value, source) for value, source in interval_candidates
                 if value is not None and value > 0),
                (None, None),
            )
            if interval is None or interval_source is None:
                raise GamePerformanceObservationError("presentmon_frame_time_invalid")
            display_value = row.get("DisplayedTime", "")
            if "DisplayedTime" not in headers:
                display_status = "unavailable"
            elif display_value is None or display_value.strip().casefold() in {"", "na", "n/a"}:
                display_status = "not_displayed"
            else:
                display_status = "displayed"

            frames.append(PresentMonFrameTiming(
                cpu_start_qpc_ms=qpc_ms,
                frame_interval_ms=interval,
                frame_interval_source=str(interval_source),
                present_interval_ms=present_interval,
                cpu_busy_ms=(
                    _optional_timeline_number(
                        row, "MsCPUBusy", invalid_reason="presentmon_cpu_busy_invalid",
                    ) if "MsCPUBusy" in headers else None
                ),
                gpu_busy_ms=(
                    _optional_timeline_number(
                        row, "MsGPUBusy", invalid_reason="presentmon_gpu_busy_invalid",
                    ) if "MsGPUBusy" in headers else None
                ),
                displayed_time_ms=displayed_time,
                display_status=display_status,
            ))
    except UnicodeError as exc:
        raise GamePerformanceObservationError("presentmon_encoding_invalid") from exc
    if not frames:
        raise GamePerformanceObservationError("presentmon_process_samples_missing")
    frames.sort(key=lambda frame: frame.cpu_start_qpc_ms)
    return tuple(frames), hashlib.sha256(raw).hexdigest()


def summarize_presentmon_timeline(
    frames: Sequence[PresentMonFrameTiming], *,
    target_frame_interval_ms: float,
    hitch_threshold_ms: float,
) -> PresentMonTimelineSummary:
    """Summarize one timing source without inferring the game's frame cap.

    Prefer display intervals, then present intervals, and use app frame timing
    only when display/present intervals are unavailable. This avoids mixing
    PresentMon v2 ``FrameTime`` fallbacks into display-time percentiles.
    """
    if (not isinstance(frames, (list, tuple))
            or not 1 <= len(frames) <= MAX_PRESENTMON_ROWS
            or any(not isinstance(frame, PresentMonFrameTiming) for frame in frames)):
        raise GamePerformanceObservationError("frame_timeline_invalid")
    for value, reason in (
        (target_frame_interval_ms, "target_frame_interval_invalid"),
        (hitch_threshold_ms, "hitch_threshold_invalid"),
    ):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(float(value)) or not 0 < float(value) <= 10_000):
            raise GamePerformanceObservationError(reason)

    display_intervals = [frame.frame_interval_ms for frame in frames
                         if frame.frame_interval_source in {
                             "MsBetweenDisplayChange", "DisplayedTime",
                         }]
    present_intervals = [frame.frame_interval_ms for frame in frames
                         if frame.frame_interval_source == "MsBetweenPresents"]
    intervals = display_intervals or present_intervals or [
        frame.frame_interval_ms for frame in frames
    ]
    p50, p95, p99, _ = summarize_frame_times_ms(intervals)
    long_flags = [interval > float(hitch_threshold_ms) for interval in intervals]
    clusters = sum(flag and (index == 0 or not long_flags[index - 1])
                   for index, flag in enumerate(long_flags))
    statuses = {frame.display_status for frame in frames}
    if not statuses <= {"displayed", "not_displayed", "unavailable"}:
        raise GamePerformanceObservationError("presentmon_display_status_invalid")
    dropped_count = (
        None if "unavailable" in statuses
        else sum(frame.display_status == "not_displayed" for frame in frames)
    )
    return PresentMonTimelineSummary(
        frame_count=len(frames),
        frame_time_p50_ms=p50,
        frame_time_p95_ms=p95,
        frame_time_p99_ms=p99,
        frame_time_max_ms=round(max(intervals), 4),
        target_frame_interval_ms=round(float(target_frame_interval_ms), 4),
        missed_deadline_count=sum(
            interval > float(target_frame_interval_ms) for interval in intervals
        ),
        hitch_threshold_ms=round(float(hitch_threshold_ms), 4),
        long_frame_count=sum(long_flags),
        long_frame_cluster_count=clusters,
        dropped_presentation_count=dropped_count,
    )


def _windows_process_sample(process_id: int) -> Mapping[str, object] | None:
    try:
        import psutil
    except ImportError:
        return None
    try:
        process = psutil.Process(process_id)
        memory = process.memory_info()
        # psutil documents the first nonblocking sample as meaningless zero.
        # A short bounded interval yields an actual per-process CPU reading.
        cpu_percent = process.cpu_percent(interval=PROCESS_CPU_SAMPLE_INTERVAL_SECONDS)
    except psutil.Error:
        return None
    return {"cpu_percent": cpu_percent, "rss_bytes": memory.rss}


def _windows_foreground_process_identity() -> tuple[int, str] | None:
    """Read the foreground PID and basename without changing process state."""
    if platform.system().casefold() != "windows":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        windll = getattr(ctypes, "windll")
        user32 = windll.user32
        kernel32 = windll.kernel32
        window = user32.GetForegroundWindow()
        if not window:
            return None
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        if not user32.GetWindowThreadProcessId(window, ctypes.byref(process_id)):
            return None
        if process_id.value < 1:
            return None
        kernel32.OpenProcess.argtypes = (
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD))
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, process_id.value)
        if not handle:
            return None
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if not kernel32.QueryFullProcessImageNameW(
                    handle, 0, buffer, ctypes.byref(size)):
                return None
            name = buffer.value.replace("\\", "/").rsplit("/", 1)[-1]
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, RuntimeError, ValueError):
        return None
    except ImportError:
        return None
    return int(process_id.value), name


def allowlisted_foreground_game_process_id(
        process_names: Sequence[str], *,
        identity_provider: Callable[[], tuple[int, str] | None] | None = None,
        ) -> int | None:
    """Return a PID only when the current foreground basename is allowlisted."""
    from .foreground_game_detection import normalize_game_process_names

    try:
        allowed = set(normalize_game_process_names(tuple(process_names)))
    except (TypeError, ValueError):
        return None
    if not allowed:
        return None
    try:
        identity = (identity_provider or _windows_foreground_process_identity)()
    except Exception:
        return None
    if (not isinstance(identity, tuple) or len(identity) != 2
            or type(identity[0]) is not int or identity[0] < 1
            or not isinstance(identity[1], str)):
        return None
    name = identity[1].strip().casefold()
    if "/" in name or "\\" in name or name not in allowed:
        return None
    return identity[0]


def _presentmon_file_sample(path: Path, process_id: int) -> tuple[tuple[float, ...], str]:
    with path.open("rb") as stream:
        raw = stream.read(MAX_PRESENTMON_BYTES + 1)
    return parse_presentmon_csv(raw, process_id=process_id)


class WindowsGamePerformanceObserver:
    """Collect frame-time and process-resource samples for one selected game PID."""

    def __init__(self, *, presentmon_csv: Path | None = None,
                 process_provider: Callable[[int], Mapping[str, object] | None] | None = None,
                 frame_provider: Callable[[int], tuple[Sequence[float], str]] | None = None,
                 system_provider: Callable[[], str] = platform.system,
                 clock: Callable[[], str] | None = None) -> None:
        self._presentmon_csv = presentmon_csv
        self._process_provider = process_provider or _windows_process_sample
        self._frame_provider = frame_provider
        self._system_provider = system_provider
        self._clock = clock or (lambda: datetime.now(timezone.utc).isoformat())

    def observe(self, process_id: int) -> GamePerformanceObservation:
        observed_at = self._clock()
        if type(process_id) is not int or process_id < 1:
            raise GamePerformanceObservationError("game_process_id_invalid")
        process_digest = hashlib.sha256(str(process_id).encode("ascii")).hexdigest()
        unsupported: list[str] = []
        if self._system_provider().casefold() != "windows":
            return GamePerformanceObservation(
                "sentientos.game_performance_observation:v1", "unsupported_platform", observed_at,
                process_digest, None, None, "unsupported", 0, None, None, None, None, None,
                ("windows_required",),
            )
        cpu_percent: float | None = None
        rss_bytes: int | None = None
        try:
            process = self._process_provider(process_id)
        except (OSError, RuntimeError, ValueError):
            process = None
            unsupported.append("process_observation_failed")
        if process is None:
            unsupported.append("process_provider_unavailable")
        else:
            cpu = process.get("cpu_percent")
            rss = process.get("rss_bytes")
            if (isinstance(cpu, bool) or not isinstance(cpu, (int, float))
                    or not math.isfinite(float(cpu)) or not 0 <= float(cpu) <= 10_000):
                unsupported.append("process_cpu_unavailable")
            else:
                cpu_percent = round(float(cpu), 4)
            if type(rss) is not int or not 0 <= rss <= 2**63 - 1:
                unsupported.append("process_rss_unavailable")
            else:
                rss_bytes = rss

        frame_source = "unsupported"
        frame_count = 0
        p50 = p95 = p99 = None
        hitch_count = None
        frame_digest = None
        try:
            if self._frame_provider is not None:
                values, frame_digest = self._frame_provider(process_id)
                frame_source = "configured_presentmon_provider"
            elif self._presentmon_csv is not None:
                values, frame_digest = _presentmon_file_sample(self._presentmon_csv, process_id)
                frame_source = "presentmon_csv"
            else:
                values = ()
                unsupported.append("presentmon_source_not_configured")
            if values:
                if not isinstance(frame_digest, str) or _SHA256.fullmatch(frame_digest) is None:
                    raise GamePerformanceObservationError("presentmon_digest_invalid")
                p50, p95, p99, hitch_count = summarize_frame_times_ms(values)
                frame_count = len(values)
            else:
                frame_digest = None
        except (OSError, GamePerformanceObservationError):
            values = ()
            frame_source = "unavailable"
            unsupported.append("presentmon_observation_unavailable")
        status = "available" if not unsupported else "partial" if cpu_percent is not None or p50 is not None else "unavailable"
        return GamePerformanceObservation(
            "sentientos.game_performance_observation:v1", status, observed_at, process_digest,
            cpu_percent, rss_bytes, frame_source, frame_count, p50, p95, p99, hitch_count,
            frame_digest, tuple(sorted(set(unsupported))),
        )


__all__ = ["GamePerformanceObservation", "GamePerformanceObservationError",
           "PresentMonFrameTiming", "PresentMonTimelineSummary",
           "WindowsGamePerformanceObserver", "parse_presentmon_csv",
           "parse_presentmon_timeline", "summarize_frame_times_ms",
           "allowlisted_foreground_game_process_id",
           "summarize_presentmon_timeline"]
