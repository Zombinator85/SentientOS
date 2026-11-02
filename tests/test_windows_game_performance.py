from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from sentientos.windows_game_performance import (
    MAX_PRESENTMON_ROWS,
    GamePerformanceObservationError,
    WindowsGamePerformanceObserver,
    parse_presentmon_csv,
    summarize_frame_times_ms,
)

pytestmark = pytest.mark.no_legacy_skip


def test_presentmon_csv_filters_pid_and_reports_hitches_without_retaining_names() -> None:
    raw = (b"ProcessID,MsBetweenPresents,Application\n"
           b"12,16.6,secret-game.exe\n12,53.0,secret-game.exe\n13,200.0,other.exe\n")
    values, source_digest = parse_presentmon_csv(raw, process_id=12)
    assert values == (16.6, 53.0)
    assert source_digest == hashlib.sha256(raw).hexdigest()
    assert summarize_frame_times_ms(values) == (16.6, 53.0, 53.0, 1)


def test_presentmon_csv_rejects_unsupported_or_empty_schema() -> None:
    with pytest.raises(GamePerformanceObservationError, match="presentmon_columns_missing"):
        parse_presentmon_csv(b"pid,frame\n1,16\n", process_id=1)
    with pytest.raises(GamePerformanceObservationError, match="presentmon_process_samples_missing"):
        parse_presentmon_csv(b"ProcessID,MsBetweenPresents\n2,16\n", process_id=1)


def test_presentmon_row_budget_counts_unselected_processes_too() -> None:
    raw = (b"ProcessID,MsBetweenPresents\n"
        + b"2,16\n" * (MAX_PRESENTMON_ROWS + 1))
    with pytest.raises(GamePerformanceObservationError, match="presentmon_row_count_exceeded"):
        parse_presentmon_csv(raw, process_id=1)


def test_linux_reports_explicit_unsupported_without_fake_zero_measurements() -> None:
    observer = WindowsGamePerformanceObserver(system_provider=lambda: "Linux")
    result = observer.observe(42)
    assert result.status == "unsupported_platform"
    assert result.process_cpu_percent is None
    assert result.process_rss_bytes is None
    assert result.frame_time_p50_ms is None
    assert result.unsupported_reasons == ("windows_required",)


def test_windows_fixture_provider_records_process_and_frame_time_observations() -> None:
    frame_digest = "a" * 64
    observer = WindowsGamePerformanceObserver(
        system_provider=lambda: "Windows",
        process_provider=lambda pid: {"cpu_percent": 42.5, "rss_bytes": 123456},
        frame_provider=lambda pid: ((16.0, 18.0, 60.0), frame_digest),
        clock=lambda: "2026-11-02T00:00:00+00:00",
    )
    result = observer.observe(987)
    assert result.status == "available"
    assert result.process_id_digest == hashlib.sha256(b"987").hexdigest()
    assert result.process_cpu_percent == 42.5
    assert result.process_rss_bytes == 123456
    assert (result.frame_time_p50_ms, result.frame_time_p95_ms,
            result.frame_time_p99_ms, result.hitch_count_over_50ms) == (18.0, 60.0, 60.0, 1)
    assert "secret-game.exe" not in repr(result.to_dict())


def test_missing_process_measurements_remain_unavailable_on_windows() -> None:
    observer = WindowsGamePerformanceObserver(system_provider=lambda: "Windows",
        process_provider=lambda pid: None)
    result = observer.observe(42)
    assert result.status == "unavailable"
    assert result.process_cpu_percent is None
    assert result.process_rss_bytes is None
    assert "process_provider_unavailable" in result.unsupported_reasons
    assert "presentmon_source_not_configured" in result.unsupported_reasons


def test_out_of_range_process_rss_is_unavailable_instead_of_poisoning_bridge_payload() -> None:
    observer = WindowsGamePerformanceObserver(system_provider=lambda: "Windows",
        process_provider=lambda pid: {"cpu_percent": 10.0, "rss_bytes": 2**63})
    result = observer.observe(42)
    assert result.process_cpu_percent == 10.0
    assert result.process_rss_bytes is None
    assert "process_rss_unavailable" in result.unsupported_reasons


def test_presentmon_file_read_is_bounded_and_provider_digest_is_validated(tmp_path: Path) -> None:
    large_file = tmp_path / "large.csv"
    large_file.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    bounded = WindowsGamePerformanceObserver(system_provider=lambda: "Windows",
        presentmon_csv=large_file, process_provider=lambda pid: None)
    result = bounded.observe(42)
    assert result.status == "unavailable"
    assert "presentmon_observation_unavailable" in result.unsupported_reasons

    malformed_digest = WindowsGamePerformanceObserver(system_provider=lambda: "Windows",
        process_provider=lambda pid: None,
        frame_provider=lambda pid: ((16.0,), "not-a-sha256"))
    invalid = malformed_digest.observe(42)
    assert invalid.frame_time_sample_count == 0
    assert invalid.frame_time_source == "unavailable"
    assert "presentmon_observation_unavailable" in invalid.unsupported_reasons
