from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, Mapping, Tuple
import sys


_EMBODIMENT_PREFIXES = (
    "avatar_",
    "emotion_",
    "presence_",
    "sensor_",
    "actuator_",
    "vision_",
    "audio_",
    "mic_",
    "speech_",
    "haptics_",
    "motion_",
    "eeg_",
)

_loaded_embodiment = [
    name
    for name in sys.modules
    if name.startswith(_EMBODIMENT_PREFIXES)
]
if _loaded_embodiment:
    raise RuntimeError(
        "ResidentKernel must be imported before embodiment modules: "
        + ", ".join(sorted(_loaded_embodiment))
    )


class KernelMisuseError(RuntimeError):
    pass


class KernelInvariantError(RuntimeError):
    pass


class KernelUnauthorizedError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class GovernanceView:
    identity_invariants: Tuple[str, str, str]
    doctrine_digest: str
    active_policy_pointer: Tuple[str, int]
    authority_flags: Mapping[str, bool]
    system_phase: str
    posture_flags: str
    constraint_rejustify_deadline: int
    last_justification_at: int
    federation_compat_digest: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class EmbodimentView:
    sensor_presence_flags: Mapping[str, bool]
    sensor_health_flags: Mapping[str, bool]
    actuator_output_state: Mapping[str, bool]
    delta_signals: Mapping[str, int]
    kernel_seq: int
    kernel_time: int


class _UpdateToken:
    pass


_UPDATE_TOKEN = _UpdateToken()


_ALLOWED_SENSORS = (
    "camera",
    "mic",
    "tactile",
    "screen",
    "haptics",
    "motion",
    "eeg",
)

_ALLOWED_ACTUATORS = (
    "screen_active",
    "audio_active",
    "haptics_active",
)

_ALLOWED_DELTAS = (
    "motion_detected",
    "audio_threshold_crossed",
)

_ALLOWED_PHASES = {
    "boot",
    "ready",
    "degraded",
    "maintenance",
    "shutdown",
}

_ALLOWED_POSTURES = {
    "normal",
    "guarded",
    "safe_brownout",
    "quarantine",
}

_ALLOWED_GOV_FIELDS = {
    "identity_invariants",
    "doctrine_digest",
    "active_policy_pointer",
    "authority_flags",
    "system_phase",
    "posture_flags",
    "constraint_rejustify_deadline",
    "last_justification_at",
    "federation_compat_digest",
}

_ALLOWED_EMB_FIELDS = {
    "sensor_presence_flags",
    "sensor_health_flags",
    "actuator_output_state",
    "delta_signals",
    "kernel_seq",
    "kernel_time",
}

_GOV_FIELD_WRITERS = {
    "identity_invariants": {"governance_arbiter"},
    "doctrine_digest": {"governance_arbiter", "doctrine_digest_builder"},
    "active_policy_pointer": {"governance_arbiter", "policy_engine"},
    "authority_flags": {"governance_arbiter", "consent_presence_gate"},
    "system_phase": {"governance_arbiter", "runtime_controller"},
    "posture_flags": {"governance_arbiter", "safety_controller"},
    "constraint_rejustify_deadline": {"governance_arbiter", "council_justifier"},
    "last_justification_at": {"governance_arbiter", "council_justifier"},
    "federation_compat_digest": {"federation_guard"},
}

_EMB_FIELD_WRITERS = {
    "sensor_presence_flags": {"governance_arbiter", "io_subsystem"},
    "sensor_health_flags": {"governance_arbiter", "io_subsystem"},
    "actuator_output_state": {"governance_arbiter", "output_controller"},
    "delta_signals": {"governance_arbiter", "signal_aggregator"},
    "kernel_seq": {"governance_arbiter"},
    "kernel_time": {"governance_arbiter"},
}

_PHASE_FIELD_ALLOWLIST = {
    "boot": {
        "identity_invariants",
        "doctrine_digest",
        "active_policy_pointer",
        "federation_compat_digest",
        "kernel_time",
        "kernel_seq",
        "system_phase",
        "posture_flags",
    },
    "ready": _ALLOWED_GOV_FIELDS | _ALLOWED_EMB_FIELDS,
    "degraded": _ALLOWED_GOV_FIELDS | _ALLOWED_EMB_FIELDS,
    "maintenance": _ALLOWED_GOV_FIELDS | _ALLOWED_EMB_FIELDS,
    "shutdown": {
        "kernel_time",
        "kernel_seq",
        "system_phase",
        "posture_flags",
    },
}

_ALLOWED_PHASE_TRANSITIONS = {
    "boot": {"ready", "degraded", "maintenance", "shutdown"},
    "ready": {"degraded", "maintenance", "shutdown"},
    "degraded": {"ready", "maintenance", "shutdown"},
    "maintenance": {"ready", "shutdown"},
    "shutdown": set(),
}


class _GovernanceState:
    __slots__ = (
        "identity_invariants",
        "doctrine_digest",
        "active_policy_pointer",
        "authority_flags",
        "system_phase",
        "posture_flags",
        "constraint_rejustify_deadline",
        "last_justification_at",
        "federation_compat_digest",
        "_sealed",
    )

    def __init__(
        self,
        *,
        identity_invariants: Tuple[str, str, str],
        doctrine_digest: str,
        active_policy_pointer: Tuple[str, int],
        authority_flags: Dict[str, bool],
        system_phase: str,
        posture_flags: str,
        constraint_rejustify_deadline: int,
        last_justification_at: int,
        federation_compat_digest: Dict[str, str],
    ) -> None:
        self._sealed = False
        self.identity_invariants = identity_invariants
        self.doctrine_digest = doctrine_digest
        self.active_policy_pointer = active_policy_pointer
        self.authority_flags = authority_flags
        self.system_phase = system_phase
        self.posture_flags = posture_flags
        self.constraint_rejustify_deadline = constraint_rejustify_deadline
        self.last_justification_at = last_justification_at
        self.federation_compat_digest = federation_compat_digest
        self._sealed = True

    def __setattr__(self, key: str, value: object) -> None:
        if getattr(self, "_sealed", False) and key != "_sealed":
            raise KernelMisuseError("GovernanceState is sealed")
        super().__setattr__(key, value)

    def _apply(self, token: _UpdateToken, **changes: object) -> None:
        if token is not _UPDATE_TOKEN:
            raise KernelUnauthorizedError("Unauthorized governance mutation")
        self._sealed = False
        for field, value in changes.items():
            super().__setattr__(field, value)
        self._sealed = True


class _EmbodimentState:
    __slots__ = (
        "sensor_presence_flags",
        "sensor_health_flags",
        "actuator_output_state",
        "delta_signals",
        "kernel_seq",
        "kernel_time",
        "_sealed",
    )

    def __init__(
        self,
        *,
        sensor_presence_flags: Dict[str, bool],
        sensor_health_flags: Dict[str, bool],
        actuator_output_state: Dict[str, bool],
        delta_signals: Dict[str, int],
        kernel_seq: int,
        kernel_time: int,
    ) -> None:
        self._sealed = False
        self.sensor_presence_flags = sensor_presence_flags
        self.sensor_health_flags = sensor_health_flags
        self.actuator_output_state = actuator_output_state
        self.delta_signals = delta_signals
        self.kernel_seq = kernel_seq
        self.kernel_time = kernel_time
        self._sealed = True

    def __setattr__(self, key: str, value: object) -> None:
        if getattr(self, "_sealed", False) and key != "_sealed":
            raise KernelMisuseError("EmbodimentState is sealed")
        super().__setattr__(key, value)

    def _apply(self, token: _UpdateToken, **changes: object) -> None:
        if token is not _UPDATE_TOKEN:
            raise KernelUnauthorizedError("Unauthorized embodiment mutation")
        self._sealed = False
        for field, value in changes.items():
            super().__setattr__(field, value)
        self._sealed = True


class ResidentKernel:
    __slots__ = ("_governance", "_embodiment")

    def __init__(self) -> None:
        self._governance = _GovernanceState(
            identity_invariants=("", "", ""),
            doctrine_digest="",
            active_policy_pointer=("", 0),
            authority_flags={
                "operator_present": False,
                "operator_verified": False,
                "automated_ok": False,
            },
            system_phase="boot",
            posture_flags="normal",
            constraint_rejustify_deadline=0,
            last_justification_at=0,
            federation_compat_digest={},
        )
        self._embodiment = _EmbodimentState(
            sensor_presence_flags={key: False for key in _ALLOWED_SENSORS},
            sensor_health_flags={key: False for key in _ALLOWED_SENSORS},
            actuator_output_state={key: False for key in _ALLOWED_ACTUATORS},
            delta_signals={key: 0 for key in _ALLOWED_DELTAS},
            kernel_seq=0,
            kernel_time=0,
        )

    def governance_view(self) -> GovernanceView:
        return GovernanceView(
            identity_invariants=self._governance.identity_invariants,
            doctrine_digest=self._governance.doctrine_digest,
            active_policy_pointer=self._governance.active_policy_pointer,
            authority_flags=MappingProxyType(dict(self._governance.authority_flags)),
            system_phase=self._governance.system_phase,
            posture_flags=self._governance.posture_flags,
            constraint_rejustify_deadline=self._governance.constraint_rejustify_deadline,
            last_justification_at=self._governance.last_justification_at,
            federation_compat_digest=MappingProxyType(
                dict(self._governance.federation_compat_digest)
            ),
        )

    def embodiment_view(self) -> EmbodimentView:
        return EmbodimentView(
            sensor_presence_flags=MappingProxyType(
                dict(self._embodiment.sensor_presence_flags)
            ),
            sensor_health_flags=MappingProxyType(
                dict(self._embodiment.sensor_health_flags)
            ),
            actuator_output_state=MappingProxyType(
                dict(self._embodiment.actuator_output_state)
            ),
            delta_signals=MappingProxyType(dict(self._embodiment.delta_signals)),
            kernel_seq=self._embodiment.kernel_seq,
            kernel_time=self._embodiment.kernel_time,
        )

    def update_governance(self, writer_id: str, **changes: object) -> None:
        self._reject_unknown_fields(changes, _ALLOWED_GOV_FIELDS)
        self._reject_unauthorized(writer_id, changes, _GOV_FIELD_WRITERS)
        self._reject_phase_mismatch(changes)
        validated = self._validate_governance_updates(changes)
        if validated:
            self._governance._apply(_UPDATE_TOKEN, **validated)

    def update_embodiment(self, writer_id: str, **changes: object) -> None:
        self._reject_unknown_fields(changes, _ALLOWED_EMB_FIELDS)
        self._reject_unauthorized(writer_id, changes, _EMB_FIELD_WRITERS)
        self._reject_phase_mismatch(changes)
        validated = self._validate_embodiment_updates(changes)
        if validated:
            self._embodiment._apply(_UPDATE_TOKEN, **validated)

    def create_checkpoint(self) -> None:
        raise NotImplementedError("Checkpoint creation is not implemented")

    def restore_checkpoint(self) -> None:
        raise NotImplementedError("Checkpoint restore is not implemented")

    def detect_corruption(self) -> None:
        raise NotImplementedError("Corruption detection is not implemented")

    def _reject_unknown_fields(self, changes: Mapping[str, object], allowed: set) -> None:
        unknown = [field for field in changes if field not in allowed]
        if unknown:
            raise KernelMisuseError(f"Unknown fields: {', '.join(sorted(unknown))}")

    def _reject_unauthorized(
        self,
        writer_id: str,
        changes: Mapping[str, object],
        field_writers: Mapping[str, set],
    ) -> None:
        for field in changes:
            allowed = field_writers.get(field, set())
            if writer_id not in allowed:
                raise KernelUnauthorizedError(
                    f"Writer '{writer_id}' cannot update '{field}'"
                )

    def _reject_phase_mismatch(self, changes: Mapping[str, object]) -> None:
        phase = self._governance.system_phase
        allowed = _PHASE_FIELD_ALLOWLIST[phase]
        for field in changes:
            if field not in allowed:
                raise KernelInvariantError(
                    f"Field '{field}' cannot update during phase '{phase}'"
                )

    def _validate_governance_updates(
        self, changes: Mapping[str, object]
    ) -> Dict[str, object]:
        updates: Dict[str, object] = {}
        if "identity_invariants" in changes:
            identity = self._validate_identity_invariants(
                changes["identity_invariants"]
            )
            if self._governance.identity_invariants != ("", "", ""):
                if identity != self._governance.identity_invariants:
                    raise KernelInvariantError("identity_invariants are immutable")
            updates["identity_invariants"] = identity
        if "doctrine_digest" in changes:
            updates["doctrine_digest"] = self._validate_digest(
                changes["doctrine_digest"],
                "doctrine_digest",
            )
        if "active_policy_pointer" in changes:
            updates["active_policy_pointer"] = self._validate_policy_pointer(
                changes["active_policy_pointer"]
            )
        if "authority_flags" in changes:
            updates["authority_flags"] = self._validate_authority_flags(
                changes["authority_flags"]
            )
        if "system_phase" in changes:
            updates["system_phase"] = self._validate_phase_change(
                changes["system_phase"]
            )
        if "posture_flags" in changes:
            updates["posture_flags"] = self._validate_posture_flags(
                changes["posture_flags"]
            )
        if "constraint_rejustify_deadline" in changes:
            updates["constraint_rejustify_deadline"] = self._validate_deadline(
                changes["constraint_rejustify_deadline"]
            )
        if "last_justification_at" in changes:
            updates["last_justification_at"] = self._validate_justification_at(
                changes["last_justification_at"]
            )
        if "federation_compat_digest" in changes:
            updates["federation_compat_digest"] = self._validate_federation_digest(
                changes["federation_compat_digest"]
            )
        return updates

    def _validate_embodiment_updates(
        self, changes: Mapping[str, object]
    ) -> Dict[str, object]:
        updates: Dict[str, object] = {}
        if "sensor_presence_flags" in changes:
            updates["sensor_presence_flags"] = self._validate_bool_map(
                changes["sensor_presence_flags"],
                _ALLOWED_SENSORS,
                "sensor_presence_flags",
            )
        if "sensor_health_flags" in changes:
            updates["sensor_health_flags"] = self._validate_bool_map(
                changes["sensor_health_flags"],
                _ALLOWED_SENSORS,
                "sensor_health_flags",
            )
            self._validate_sensor_health(updates["sensor_health_flags"])
        if "actuator_output_state" in changes:
            updates["actuator_output_state"] = self._validate_bool_map(
                changes["actuator_output_state"],
                _ALLOWED_ACTUATORS,
                "actuator_output_state",
            )
            self._validate_actuator_state(updates["actuator_output_state"])
        if "delta_signals" in changes:
            updates["delta_signals"] = self._validate_counter_map(
                changes["delta_signals"],
                _ALLOWED_DELTAS,
                "delta_signals",
                self._embodiment.delta_signals,
            )
        if "kernel_seq" in changes:
            updates["kernel_seq"] = self._validate_monotonic_int(
                changes["kernel_seq"],
                self._embodiment.kernel_seq,
                "kernel_seq",
            )
        if "kernel_time" in changes:
            updates["kernel_time"] = self._validate_monotonic_int(
                changes["kernel_time"],
                self._embodiment.kernel_time,
                "kernel_time",
            )
        return updates

    def _validate_identity_invariants(self, value: object) -> Tuple[str, str, str]:
        if not isinstance(value, tuple) or len(value) != 3:
            raise KernelInvariantError("identity_invariants must be a 3-tuple")
        if not all(isinstance(item, str) and item for item in value):
            raise KernelInvariantError("identity_invariants must be non-empty strings")
        return value

    def _validate_digest(self, value: object, field: str) -> str:
        if not isinstance(value, str) or not value:
            raise KernelInvariantError(f"{field} must be a non-empty string")
        return value

    def _validate_policy_pointer(self, value: object) -> Tuple[str, int]:
        if not isinstance(value, tuple) or len(value) != 2:
            raise KernelInvariantError("active_policy_pointer must be a 2-tuple")
        policy_id, version = value
        if not isinstance(policy_id, str) or not policy_id:
            raise KernelInvariantError("policy_id must be a non-empty string")
        if not isinstance(version, int) or version < 0:
            raise KernelInvariantError("policy version must be a non-negative int")
        return policy_id, version

    def _validate_authority_flags(self, value: object) -> Dict[str, bool]:
        required = {"operator_present", "operator_verified", "automated_ok"}
        if not isinstance(value, Mapping):
            raise KernelInvariantError("authority_flags must be a mapping")
        if set(value.keys()) != required:
            raise KernelInvariantError("authority_flags must contain fixed keys")
        if not all(isinstance(value[key], bool) for key in required):
            raise KernelInvariantError("authority_flags values must be bools")
        if value["operator_verified"] and not value["operator_present"]:
            raise KernelInvariantError(
                "operator_verified requires operator_present"
            )
        if value["automated_ok"] and self._governance.active_policy_pointer == ("", 0):
            raise KernelInvariantError("automated_ok requires active_policy_pointer")
        return {key: value[key] for key in required}

    def _validate_phase_change(self, value: object) -> str:
        if not isinstance(value, str) or value not in _ALLOWED_PHASES:
            raise KernelInvariantError("system_phase must be a known phase")
        current = self._governance.system_phase
        if value == current:
            return value
        if value not in _ALLOWED_PHASE_TRANSITIONS.get(current, set()):
            raise KernelInvariantError(
                f"Invalid phase transition: {current} -> {value}"
            )
        return value

    def _validate_posture_flags(self, value: object) -> str:
        if not isinstance(value, str) or value not in _ALLOWED_POSTURES:
            raise KernelInvariantError("posture_flags must be a known posture")
        return value

    def _validate_deadline(self, value: object) -> int:
        if not isinstance(value, int) or value < 0:
            raise KernelInvariantError("constraint_rejustify_deadline must be int")
        if value < self._governance.last_justification_at:
            raise KernelInvariantError("deadline must be >= last_justification_at")
        return value

    def _validate_justification_at(self, value: object) -> int:
        if not isinstance(value, int) or value < 0:
            raise KernelInvariantError("last_justification_at must be int")
        if value < self._governance.last_justification_at:
            raise KernelInvariantError("last_justification_at must be monotonic")
        return value

    def _validate_federation_digest(self, value: object) -> Dict[str, str]:
        if not isinstance(value, Mapping):
            raise KernelInvariantError("federation_compat_digest must be a mapping")
        validated: Dict[str, str] = {}
        for key, digest in value.items():
            if not isinstance(key, str) or not key:
                raise KernelInvariantError("federation keys must be strings")
            if not isinstance(digest, str) or not digest:
                raise KernelInvariantError("federation digests must be strings")
            validated[key] = digest
        return validated

    def _validate_bool_map(
        self, value: object, allowed_keys: Tuple[str, ...], field: str
    ) -> Dict[str, bool]:
        if not isinstance(value, Mapping):
            raise KernelInvariantError(f"{field} must be a mapping")
        if set(value.keys()) != set(allowed_keys):
            raise KernelInvariantError(f"{field} keys must be fixed")
        if not all(isinstance(value[key], bool) for key in allowed_keys):
            raise KernelInvariantError(f"{field} values must be bools")
        return {key: value[key] for key in allowed_keys}

    def _validate_counter_map(
        self,
        value: object,
        allowed_keys: Tuple[str, ...],
        field: str,
        current: Mapping[str, int],
    ) -> Dict[str, int]:
        if not isinstance(value, Mapping):
            raise KernelInvariantError(f"{field} must be a mapping")
        if set(value.keys()) != set(allowed_keys):
            raise KernelInvariantError(f"{field} keys must be fixed")
        validated: Dict[str, int] = {}
        for key in allowed_keys:
            counter = value[key]
            if not isinstance(counter, int) or counter < 0:
                raise KernelInvariantError(f"{field} values must be non-negative ints")
            if counter < current.get(key, 0):
                raise KernelInvariantError(f"{field} values must be monotonic")
            validated[key] = counter
        return validated

    def _validate_monotonic_int(self, value: object, current: int, field: str) -> int:
        if not isinstance(value, int) or value < 0:
            raise KernelInvariantError(f"{field} must be a non-negative int")
        if value < current:
            raise KernelInvariantError(f"{field} must be monotonic")
        return value

    def _validate_sensor_health(self, health: Mapping[str, bool]) -> None:
        for key, is_healthy in health.items():
            if is_healthy and not self._embodiment.sensor_presence_flags.get(key, False):
                raise KernelInvariantError("sensor health requires presence")

    def _validate_actuator_state(self, state: Mapping[str, bool]) -> None:
        phase = self._governance.system_phase
        if phase not in {"ready", "degraded"}:
            if any(state.values()):
                raise KernelInvariantError("actuator outputs require ready/degraded")


__all__ = [
    "EmbodimentView",
    "GovernanceView",
    "KernelInvariantError",
    "KernelMisuseError",
    "KernelUnauthorizedError",
    "ResidentKernel",
]
