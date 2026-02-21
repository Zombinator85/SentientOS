from __future__ import annotations

from sentientos.integrity_quarantine import QuarantineState
from sentientos.throughput_policy import derive_throughput_policy


def test_mode_derivation_from_pressure_levels() -> None:
    assert derive_throughput_policy(integrity_pressure_level=0).mode == "normal"
    assert derive_throughput_policy(integrity_pressure_level=1).mode == "cautious"
    assert derive_throughput_policy(integrity_pressure_level=2).mode == "recovery"
    assert derive_throughput_policy(integrity_pressure_level=3).mode == "lockdown"


def test_quarantine_forces_lockdown() -> None:
    quarantine = QuarantineState(active=True, freeze_forge=True)
    policy = derive_throughput_policy(integrity_pressure_level=1, quarantine=quarantine)
    assert policy.mode == "lockdown"
    assert policy.allow_forge_mutation is False


def test_env_overrides(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SENTIENTOS_MODE_FORCE", "cautious")
    monkeypatch.setenv("SENTIENTOS_MODE_ALLOW_AUTOMERGE", "1")
    policy = derive_throughput_policy(integrity_pressure_level=3)
    assert policy.mode == "cautious"
    assert policy.allow_automerge is True
