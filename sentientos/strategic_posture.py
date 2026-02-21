from __future__ import annotations

from dataclasses import dataclass
import math
import os
from typing import Literal

PostureName = Literal["stability", "balanced", "velocity"]


@dataclass(frozen=True, slots=True)
class StrategicPostureConfig:
    posture: PostureName
    warn_multiplier: float
    enforce_multiplier: float
    critical_multiplier: float
    throughput_cautious_level: int
    throughput_recovery_level: int
    throughput_lockdown_level: int
    high_severity_enforce_level: int
    quarantine_auto_sensitivity: Literal["strict", "balanced", "lenient"]
    quarantine_force_level: int
    default_automerge_enabled: bool
    default_canary_publish_enabled: bool
    default_merge_train_enabled: bool
    default_federation_enforce: bool
    default_audit_strict: bool
    diagnostics_sweep_interval_minutes: int


_POSTURES: dict[PostureName, StrategicPostureConfig] = {
    "stability": StrategicPostureConfig(
        posture="stability",
        warn_multiplier=0.8,
        enforce_multiplier=0.8,
        critical_multiplier=0.8,
        throughput_cautious_level=1,
        throughput_recovery_level=2,
        throughput_lockdown_level=2,
        high_severity_enforce_level=1,
        quarantine_auto_sensitivity="strict",
        quarantine_force_level=2,
        default_automerge_enabled=True,
        default_canary_publish_enabled=True,
        default_merge_train_enabled=False,
        default_federation_enforce=True,
        default_audit_strict=True,
        diagnostics_sweep_interval_minutes=10,
    ),
    "balanced": StrategicPostureConfig(
        posture="balanced",
        warn_multiplier=1.0,
        enforce_multiplier=1.0,
        critical_multiplier=1.0,
        throughput_cautious_level=1,
        throughput_recovery_level=2,
        throughput_lockdown_level=3,
        high_severity_enforce_level=2,
        quarantine_auto_sensitivity="balanced",
        quarantine_force_level=3,
        default_automerge_enabled=True,
        default_canary_publish_enabled=False,
        default_merge_train_enabled=False,
        default_federation_enforce=False,
        default_audit_strict=False,
        diagnostics_sweep_interval_minutes=20,
    ),
    "velocity": StrategicPostureConfig(
        posture="velocity",
        warn_multiplier=1.3,
        enforce_multiplier=1.3,
        critical_multiplier=1.3,
        throughput_cautious_level=2,
        throughput_recovery_level=3,
        throughput_lockdown_level=4,
        high_severity_enforce_level=3,
        quarantine_auto_sensitivity="lenient",
        quarantine_force_level=4,
        default_automerge_enabled=True,
        default_canary_publish_enabled=False,
        default_merge_train_enabled=True,
        default_federation_enforce=False,
        default_audit_strict=False,
        diagnostics_sweep_interval_minutes=45,
    ),
}


def resolve_posture() -> StrategicPostureConfig:
    raw = os.getenv("SENTIENTOS_POSTURE", "balanced")
    normalized = raw.strip().lower()
    if normalized in _POSTURES:
        return _POSTURES[normalized]  # type: ignore[index]
    return _POSTURES["balanced"]


def scaled_threshold(base: int, multiplier: float) -> int:
    return max(1, int(math.ceil(base * multiplier)))


def env_bool(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    return raw.strip() == "1"


def env_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def gate_enforce_default(gate_name: str, config: StrategicPostureConfig) -> bool:
    if gate_name == "federation":
        return config.default_federation_enforce
    if gate_name == "audit_chain":
        return config.default_audit_strict
    return False


def derived_thresholds(config: StrategicPostureConfig, *, warn_base: int, enforce_base: int, critical_base: int) -> dict[str, int]:
    warn = scaled_threshold(warn_base, config.warn_multiplier)
    enforce = max(warn + 1, scaled_threshold(enforce_base, config.enforce_multiplier))
    critical = max(enforce + 1, scaled_threshold(critical_base, config.critical_multiplier))
    return {"warn": warn, "enforce": enforce, "critical": critical}
