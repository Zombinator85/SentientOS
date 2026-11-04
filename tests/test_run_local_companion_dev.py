from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.no_legacy_skip


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
