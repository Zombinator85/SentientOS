from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.no_legacy_skip


def test_screen_ocr_executable_path_is_converted_for_windows_edge():
    from scripts.run_local_companion_dev import _normalize_windows_edge_executable

    conversions = []
    def convert(path):
        conversions.append(path)
        return r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    assert _normalize_windows_edge_executable(
        "/mnt/c/Program Files/Tesseract-OCR/tesseract.exe",
        convert_wsl_path=convert) == r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    assert conversions == [Path("/mnt/c/Program Files/Tesseract-OCR/tesseract.exe")]
    assert _normalize_windows_edge_executable(
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        convert_wsl_path=convert) == r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    assert _normalize_windows_edge_executable(
        "tesseract.exe", convert_wsl_path=convert) == "tesseract.exe"
    with pytest.raises(ValueError, match="screen_observation_ocr_windows_path_required"):
        _normalize_windows_edge_executable(
            "/usr/bin/tesseract", convert_wsl_path=convert)


def test_host_resource_log_exposes_timestamped_cpu_ram_gpu_and_vram():
    from scripts.run_local_companion_dev import _host_resource_log_payload

    evaluation = SimpleNamespace(
        snapshot=SimpleNamespace(
            cpu_utilization_percent=31.5,
            ram_utilization_percent=62.0,
            gpu_utilization_percent=84.0,
            vram_utilization_percent=81.25,
        ),
        epoch=SimpleNamespace(
            observed_at="2026-11-04T18:00:00+00:00",
            collectors_called=4,
            status_counts={"ok": 4},
        ),
        pressure_report=SimpleNamespace(pressure_labels=("nominal",)),
        no_effect_authority=True,
    )

    event = _host_resource_log_payload(evaluation, {
        "evaluation_id": "hre-test",
        "status": "ok",
    })

    assert event == {
        "event": "host_resource_observation",
        "evaluation_id": "hre-test",
        "status": "ok",
        "observed_at": "2026-11-04T18:00:00+00:00",
        "pressure_labels": ["nominal"],
        "collectors_called": 4,
        "collector_status_counts": {"ok": 4},
        "cpu_utilization_percent": 31.5,
        "ram_utilization_percent": 62.0,
        "gpu_utilization_percent": 84.0,
        "vram_utilization_percent": 81.25,
        "gpu_telemetry_available": True,
        "no_effect_authority": True,
        "host_mutation_performed": False,
    }


def test_host_resource_log_marks_missing_gpu_telemetry():
    from scripts.run_local_companion_dev import _host_resource_log_payload

    evaluation = SimpleNamespace(
        snapshot=SimpleNamespace(
            cpu_utilization_percent=None,
            ram_utilization_percent=None,
            gpu_utilization_percent=None,
            vram_utilization_percent=None,
        ),
        epoch=SimpleNamespace(
            observed_at="2026-11-04T18:00:00+00:00",
            collectors_called=3,
            status_counts={"ok": 2, "unavailable": 1},
        ),
        pressure_report=SimpleNamespace(pressure_labels=("telemetry_incomplete",)),
        no_effect_authority=True,
    )

    event = _host_resource_log_payload(evaluation, {
        "evaluation_id": "hre-missing-gpu",
        "status": "degraded",
    })

    assert event["gpu_telemetry_available"] is False
    assert event["cpu_utilization_percent"] is None
    assert event["ram_utilization_percent"] is None
    assert event["gpu_utilization_percent"] is None
    assert event["vram_utilization_percent"] is None
    assert event["host_mutation_performed"] is False


@pytest.mark.parametrize(("samples", "expected"), [
    ((), "deferred"),
    ((80.0,), "available"),
    ((85.0,), "deferred"),
    ((85.0, 83.0), "deferred"),
    ((85.0, 81.9), "available"),
    ((80.0, None), "deferred"),
])
def test_gaming_resource_pressure_guard_uses_fail_closed_hysteresis(samples, expected):
    from scripts.run_local_companion_dev import _GamingResourcePressureGuard

    guard = _GamingResourcePressureGuard()
    assert guard.is_blocked() is True
    state = guard.status()
    for index, sample in enumerate(samples):
        state = guard.observe(sample, f"2026-11-06T09:00:{index:02d}+00:00")
    assert state["admission_status"] == expected
    assert guard.is_blocked() is (expected == "deferred")
    if samples and samples[-1] is None:
        assert state["reason_code"] == "vram_telemetry_unavailable"


def test_gaming_resource_pressure_guard_blocks_after_observation_goes_stale(monkeypatch):
    import scripts.run_local_companion_dev as runner

    guard = runner._GamingResourcePressureGuard()
    guard.observe(80.0, "2026-11-06T09:00:00+00:00")
    observed_at = guard._last_observed_monotonic
    assert observed_at is not None
    monkeypatch.setattr(runner.time, "monotonic", lambda: observed_at + 46.0)

    state = guard.status()

    assert state["admission_status"] == "deferred"
    assert state["reason_code"] == "vram_telemetry_stale"


def test_gaming_resource_observation_releases_residency_when_gate_closes():
    from scripts.run_local_companion_dev import (
        _GamingResourcePressureGuard, _apply_gaming_resource_observation,
    )

    guard = _GamingResourcePressureGuard()
    releases = []
    release = lambda reason: releases.append(reason) or {"status": "released"}
    available = _apply_gaming_resource_observation(
        guard, 80.0, "2026-11-06T09:00:00+00:00", release)
    assert available["admission_status"] == "available"
    assert releases == []

    pressured = _apply_gaming_resource_observation(
        guard, 91.0, "2026-11-06T09:00:15+00:00", release)
    assert pressured["admission_status"] == "deferred"
    assert pressured["residency_release"] == {"status": "released"}
    assert releases == ["vram_pressure_observed"]

    _apply_gaming_resource_observation(
        guard, None, None, release)
    assert releases[-1] == "vram_telemetry_unavailable"


def test_gaming_resource_pressure_guard_rejects_invalid_percentages():
    from scripts.run_local_companion_dev import _GamingResourcePressureGuard

    guard = _GamingResourcePressureGuard()
    for invalid in (-0.1, 100.1, True, float("nan"), "90"):
        state = guard.observe(invalid, "2026-11-06T09:00:00+00:00")
        assert state["admission_status"] == "deferred"
        assert state["reason_code"] == "vram_telemetry_unavailable"


def test_gaming_preload_requires_additional_vram_headroom():
    from scripts.run_local_companion_dev import _GamingResourcePressureGuard

    guard = _GamingResourcePressureGuard()
    available = guard.observe(74.9, "2026-11-06T09:00:00+00:00")
    assert available["admission_status"] == "available"
    assert available["preload_admission_status"] == "available"
    assert available["preload_threshold_percent"] == 75.0

    warm_denied = guard.observe(75.0, "2026-11-06T09:00:15+00:00")
    assert warm_denied["admission_status"] == "available"
    assert warm_denied["preload_admission_status"] == "deferred"
    assert warm_denied["preload_reason_code"] == "preload_vram_headroom_insufficient"
