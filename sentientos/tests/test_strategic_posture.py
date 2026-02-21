from __future__ import annotations

from datetime import datetime

from sentientos.integrity_pressure import compute_integrity_pressure
from sentientos.throughput_policy import derive_throughput_policy


def test_posture_modifies_thresholds_deterministically(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_POSTURE", "stability")
    stability = compute_integrity_pressure(tmp_path, now=datetime.fromisoformat("2026-01-01T00:00:00+00:00"))
    monkeypatch.setenv("SENTIENTOS_POSTURE", "balanced")
    balanced = compute_integrity_pressure(tmp_path, now=datetime.fromisoformat("2026-01-01T00:00:00+00:00"))
    monkeypatch.setenv("SENTIENTOS_POSTURE", "velocity")
    velocity = compute_integrity_pressure(tmp_path, now=datetime.fromisoformat("2026-01-01T00:00:00+00:00"))

    assert stability.warn_threshold <= balanced.warn_threshold <= velocity.warn_threshold
    assert stability.enforce_threshold < balanced.enforce_threshold < velocity.enforce_threshold
    assert stability.critical_threshold < balanced.critical_threshold < velocity.critical_threshold


def test_velocity_posture_reduces_pressure_sensitivity(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_POSTURE", "velocity")
    assert derive_throughput_policy(integrity_pressure_level=1).mode == "normal"


def test_stability_posture_escalates_faster(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_POSTURE", "stability")
    assert derive_throughput_policy(integrity_pressure_level=2).mode == "lockdown"


def test_env_overrides_still_win(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_POSTURE", "stability")
    monkeypatch.setenv("SENTIENTOS_PRESSURE_WARN_THRESHOLD", "9")
    snapshot = compute_integrity_pressure(tmp_path, now=datetime.fromisoformat("2026-01-01T00:00:00+00:00"))
    assert snapshot.warn_threshold == 9
