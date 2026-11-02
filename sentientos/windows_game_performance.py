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


def parse_presentmon_csv(raw: bytes, *, process_id: int) -> tuple[tuple[float, ...], str]:
    """Parse a bounded PresentMon export without retaining executable names or paths."""
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_PRESENTMON_BYTES:
        raise GamePerformanceObservationError("presentmon_input_size_invalid")
    if type(process_id) is not int or process_id < 1:
        raise GamePerformanceObservationError("game_process_id_invalid")
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = set(reader.fieldnames or ())
        if not {"ProcessID", "MsBetweenPresents"}.issubset(headers):
            raise GamePerformanceObservationError("presentmon_columns_missing")
        times: list[float] = []
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
            try:
                sample = float(row["MsBetweenPresents"] or "")
            except (TypeError, ValueError) as exc:
                raise GamePerformanceObservationError("presentmon_frame_time_invalid") from exc
            if not math.isfinite(sample) or sample <= 0 or sample > 10_000:
                raise GamePerformanceObservationError("presentmon_frame_time_invalid")
            times.append(sample)
    except UnicodeError as exc:
        raise GamePerformanceObservationError("presentmon_encoding_invalid") from exc
    if not times:
        raise GamePerformanceObservationError("presentmon_process_samples_missing")
    return tuple(times), hashlib.sha256(raw).hexdigest()


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
           "WindowsGamePerformanceObserver", "parse_presentmon_csv", "summarize_frame_times_ms"]
