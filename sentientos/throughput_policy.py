from __future__ import annotations

from dataclasses import asdict, dataclass
import os

from sentientos.integrity_quarantine import QuarantineState


@dataclass(slots=True)
class ThroughputPolicy:
    mode: str
    allow_automerge: bool
    allow_publish: bool
    allow_forge_mutation: bool
    allow_federation_adopt: bool
    run_integrity_sweeps: bool
    prefer_diagnostics_only: bool
    max_forge_scope: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def derive_throughput_policy(*, integrity_pressure_level: int, quarantine: QuarantineState | None = None) -> ThroughputPolicy:
    forced_mode = _env_mode("SENTIENTOS_MODE_FORCE")
    if forced_mode is not None:
        mode = forced_mode
    elif quarantine is not None and quarantine.active and quarantine.freeze_forge:
        mode = "lockdown"
    elif integrity_pressure_level >= 3:
        mode = "lockdown"
    elif integrity_pressure_level >= 2:
        mode = "recovery"
    elif integrity_pressure_level >= 1:
        mode = "cautious"
    else:
        mode = "normal"

    policy = _defaults_for_mode(mode)
    auto_override = _env_bool("SENTIENTOS_MODE_ALLOW_AUTOMERGE")
    if auto_override is not None:
        policy.allow_automerge = auto_override
    publish_override = _env_bool("SENTIENTOS_MODE_ALLOW_PUBLISH")
    if publish_override is not None:
        policy.allow_publish = publish_override
    return policy


def _defaults_for_mode(mode: str) -> ThroughputPolicy:
    if mode == "normal":
        return ThroughputPolicy(mode=mode, allow_automerge=True, allow_publish=True, allow_forge_mutation=True, allow_federation_adopt=True, run_integrity_sweeps=False, prefer_diagnostics_only=False, max_forge_scope=200)
    if mode == "cautious":
        return ThroughputPolicy(mode=mode, allow_automerge=False, allow_publish=False, allow_forge_mutation=True, allow_federation_adopt=True, run_integrity_sweeps=True, prefer_diagnostics_only=False, max_forge_scope=80)
    if mode == "recovery":
        return ThroughputPolicy(mode=mode, allow_automerge=False, allow_publish=False, allow_forge_mutation=False, allow_federation_adopt=False, run_integrity_sweeps=True, prefer_diagnostics_only=True, max_forge_scope=25)
    return ThroughputPolicy(mode="lockdown", allow_automerge=False, allow_publish=False, allow_forge_mutation=False, allow_federation_adopt=False, run_integrity_sweeps=True, prefer_diagnostics_only=True, max_forge_scope=0)


def _env_mode(name: str) -> str | None:
    value = os.getenv(name)
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered in {"normal", "cautious", "recovery", "lockdown"}:
        return lowered
    return None


def _env_bool(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip() == "1"
