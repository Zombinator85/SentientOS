from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from sentientos.windows_game_performance import (
    MAX_PRESENTMON_ROWS,
    GamePerformanceObservationError,
    WindowsGamePerformanceObserver,
    allowlisted_game_process_id,
    parse_presentmon_csv,
    parse_presentmon_timeline,
    summarize_frame_times_ms,
    summarize_presentmon_timeline,
)

pytestmark = pytest.mark.no_legacy_skip


def test_game_process_selection_prefers_allowlisted_foreground_then_running_game():
    identity = [1234, "Cronos.exe"]
    provider = lambda: (identity[0], identity[1])
    assert allowlisted_game_process_id(
        ["Cronos.exe"], identity_provider=provider) == 1234
    assert allowlisted_game_process_id(["OtherGame.exe"],
        identity_provider=provider, running_identities_provider=lambda: (
            (44, "OtherGame.exe"),)) == 44
    assert allowlisted_game_process_id(["Cronos.exe"],
        identity_provider=lambda: (1, "explorer.exe"),
        running_identities_provider=lambda: (
            (99, "Cronos.exe"), (87, "Cronos.exe"))) == 87
    assert allowlisted_game_process_id(["OtherGame.exe"],
        identity_provider=lambda: (0, "Cronos.exe"),
        running_identities_provider=lambda: ()) is None
    assert allowlisted_game_process_id([], identity_provider=provider) is None


def test_presentmon_csv_filters_pid_and_reports_hitches_without_retaining_names() -> None:
    raw = (b"ProcessID,MsBetweenPresents,Application\n"
           b"12,16.6,secret-game.exe\n12,53.0,secret-game.exe\n13,200.0,other.exe\n")
    values, source_digest = parse_presentmon_csv(raw, process_id=12)
    assert values == (16.6, 53.0)
    assert source_digest == hashlib.sha256(raw).hexdigest()
    assert summarize_frame_times_ms(values) == (16.6, 53.0, 53.0, 1)


def test_presentmon_csv_prefers_displayed_frame_intervals() -> None:
    raw = b"\n".join((
        b"ProcessID,MsBetweenPresents,MsBetweenDisplayChange",
        b"12,16.6,33.3",
        b"12,16.7,50.1",
        b"13,200.0,300.0",
    )) + b"\n"
    values, source_digest = parse_presentmon_csv(raw, process_id=12)
    assert values == (33.3, 50.1)
    assert source_digest == hashlib.sha256(raw).hexdigest()
    assert summarize_frame_times_ms(values) == (33.3, 50.1, 50.1, 1)


def test_presentmon_v2_csv_uses_displayed_time_and_falls_back_to_frame_time() -> None:
    raw = b"\n".join((
        b"ProcessID,CPUStartQPCTime,FrameTime,DisplayedTime",
        b"12,1000.0,16.0,16.2",
        b"12,1016.0,17.0,NA",
        b"12,1033.0,50.0,50.4",
        b"13,1083.0,200.0,200.0",
    )) + b"\n"
    values, source_digest = parse_presentmon_csv(raw, process_id=12)
    assert values == (16.2, 50.4)
    assert source_digest == hashlib.sha256(raw).hexdigest()

    no_display_metrics = b"ProcessID,FrameTime,DisplayedTime\n12,16.0,NA\n12,33.0,NA\n"
    fallback, _ = parse_presentmon_csv(no_display_metrics, process_id=12)
    assert fallback == (16.0, 33.0)


def test_presentmon_redirected_windows_csv_accepts_bom_marked_utf16() -> None:
    raw = "ProcessID,MsBetweenDisplayChange,MsBetweenPresents\r\n12,16.4,16.2\r\n".encode(
        "utf-16"
    )
    values, source_digest = parse_presentmon_csv(raw, process_id=12)
    assert values == (16.4,)
    assert source_digest == hashlib.sha256(raw).hexdigest()

    timeline_raw = (
        "ProcessID,CPUStartQPCTime,FrameTime,DisplayedTime\r\n"
        "12,1000.0,16.0,16.4\r\n"
    ).encode("utf-16")
    frames, timeline_digest = parse_presentmon_timeline(timeline_raw, process_id=12)
    assert timeline_digest == hashlib.sha256(timeline_raw).hexdigest()
    assert frames[0].frame_interval_ms == 16.4
    assert frames[0].frame_interval_source == "DisplayedTime"


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
        process_provider=lambda pid: {"name": "secret-game.exe",
            "cpu_percent": 42.5, "rss_bytes": 123456},
        frame_provider=lambda pid: ((16.0, 18.0, 60.0), frame_digest),
        clock=lambda: "2026-11-02T00:00:00+00:00",
    )
    result = observer.observe(987)
    assert result.status == "available"
    assert result.process_id_digest == hashlib.sha256(b"987").hexdigest()
    assert result.process_name_digest == hashlib.sha256(b"secret-game.exe").hexdigest()
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


def test_presentmon_experimental_timeline_keeps_qpc_cpu_gpu_and_display_status() -> None:
    raw = bytes((10,)).join((
        b"ProcessID,CPUStartQPCTime,MsBetweenDisplayChange,MsBetweenPresents,"
        b"MsCPUBusy,MsGPUBusy,DisplayedTime",
        b"12,2016.7,33.3,16.7,31.2,28.4,33.3",
        b"13,2020.0,60.0,60.0,55.0,50.0,60.0",
        b"12,2000.0,16.7,16.6,8.2,7.4,NA",
    )) + bytes((10,))
    frames, source_digest = parse_presentmon_timeline(raw, process_id=12)
    assert source_digest == hashlib.sha256(raw).hexdigest()
    assert [frame.cpu_start_qpc_ms for frame in frames] == [2000.0, 2016.7]
    assert frames[0].frame_interval_ms == 16.7
    assert frames[0].present_interval_ms == 16.6
    assert frames[0].cpu_busy_ms == 8.2
    assert frames[0].gpu_busy_ms == 7.4
    assert frames[0].display_status == "not_displayed"
    assert frames[0].displayed_time_ms is None
    assert frames[1].frame_interval_ms == 33.3
    assert frames[1].display_status == "displayed"
    assert frames[1].displayed_time_ms == 33.3


def test_presentmon_v2_timeline_keeps_app_frame_and_actual_display_timing() -> None:
    raw = b"\n".join((
        b"ProcessID,CPUStartQPCTime,FrameTime,CPUBusy,CPUWait,DisplayedTime",
        b"12,1016.0,16.0,14.0,2.0,16.1",
        b"12,1000.0,15.0,13.0,2.0,NA",
        b"12,1032.0,30.0,28.0,2.0,32.2",
    )) + b"\n"
    frames, digest = parse_presentmon_timeline(raw, process_id=12)
    assert digest == hashlib.sha256(raw).hexdigest()
    assert [frame.cpu_start_qpc_ms for frame in frames] == [1000.0, 1016.0, 1032.0]
    assert [frame.frame_interval_ms for frame in frames] == [15.0, 16.1, 32.2]
    assert [frame.display_status for frame in frames] == [
        "not_displayed", "displayed", "displayed",
    ]
    assert [frame.frame_interval_source for frame in frames] == [
        "FrameTime", "DisplayedTime", "DisplayedTime",
    ]
    assert [frame.displayed_time_ms for frame in frames] == [None, 16.1, 32.2]
    summary = summarize_presentmon_timeline(
        frames, target_frame_interval_ms=16.7, hitch_threshold_ms=50.0,
    )
    assert summary.frame_time_p50_ms == 16.1
    assert summary.frame_time_p95_ms == 32.2
    assert summary.missed_deadline_count == 1
    assert summary.dropped_presentation_count == 1


def test_presentmon_qpc_time_ms_output_header_is_accepted() -> None:
    raw = b"\n".join((
        b"ProcessID,CPUStartQPCTimeInMs,MsBetweenDisplayChange,MsBetweenPresents",
        b"12,2000.0,16.7,16.6",
        b"12,2016.7,33.3,33.3",
    )) + b"\n"
    frames, _ = parse_presentmon_timeline(raw, process_id=12)
    assert [frame.cpu_start_qpc_ms for frame in frames] == [2000.0, 2016.7]
    summary = summarize_presentmon_timeline(
        frames, target_frame_interval_ms=16.7, hitch_threshold_ms=50.0,
    )
    assert summary.frame_time_p50_ms == 16.7
    assert summary.frame_time_p95_ms == 33.3


def test_presentmon_experimental_timeline_requires_qpc_timestamp_and_valid_values() -> None:
    with pytest.raises(GamePerformanceObservationError,
                       match="presentmon_timeline_columns_missing"):
        parse_presentmon_timeline(
            b"ProcessID,MsBetweenPresents" + bytes((10,)) + b"12,16.6" + bytes((10,)),
            process_id=12,
        )
    raw = (b"ProcessID,CPUStartQPCTime,MsBetweenPresents" + bytes((10,)) +
           b"12,NA,16.6" + bytes((10,)))
    with pytest.raises(GamePerformanceObservationError, match="presentmon_timestamp_invalid"):
        parse_presentmon_timeline(raw, process_id=12)


def test_presentmon_timeline_summary_uses_explicit_target_and_counts_hitch_clusters() -> None:
    raw = bytes((10,)).join((
        b"ProcessID,CPUStartQPCTime,MsBetweenDisplayChange,MsBetweenPresents,DisplayedTime",
        b"12,1000.0,16.7,16.6,16.7",
        b"12,1016.7,33.3,33.3,33.3",
        b"12,1050.0,66.7,66.7,NA",
        b"12,1116.7,70.0,70.0,NA",
    )) + bytes((10,))
    frames, _ = parse_presentmon_timeline(raw, process_id=12)
    summary = summarize_presentmon_timeline(
        frames, target_frame_interval_ms=16.8, hitch_threshold_ms=50.0,
    )
    assert summary.frame_count == 4
    assert summary.frame_time_p50_ms == 33.3
    assert summary.frame_time_p95_ms == 70.0
    assert summary.frame_time_p99_ms == 70.0
    assert summary.frame_time_max_ms == 70.0
    assert summary.missed_deadline_count == 3
    assert summary.long_frame_count == 2
    assert summary.long_frame_cluster_count == 1
    assert summary.dropped_presentation_count == 2
