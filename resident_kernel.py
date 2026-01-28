from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from types import MappingProxyType
from typing import Dict, Mapping, Tuple

from embodiment.silhouette_store import load_recent_silhouettes
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

_KERNEL_VERSION = "resident-kernel-v1"

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

_logger = logging.getLogger(__name__)


class KernelMisuseError(RuntimeError):
    pass


class KernelInvariantError(RuntimeError):
    pass


class KernelUnauthorizedError(PermissionError):
    pass


class KernelCorruptionError(RuntimeError):
    pass


class KernelWriteOutsideEpochError(RuntimeError):
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
    kernel_epoch: int


@dataclass(frozen=True, slots=True)
class EmbodimentView:
    sensor_presence_flags: Mapping[str, bool]
    sensor_health_flags: Mapping[str, bool]
    actuator_output_state: Mapping[str, bool]
    delta_signals: Mapping[str, int]
    kernel_seq: int
    kernel_time: int


@dataclass(frozen=True, slots=True)
class KernelCheckpoint:
    version: str
    governance: Mapping[str, object]
    embodiment: Mapping[str, object]
    digest: str


@dataclass(frozen=True, slots=True)
class KernelEpochAudit:
    epoch_id: int
    writer_id: str
    kernel_seq: int
    kernel_time: int
    fields_touched: Tuple[str, ...]
    rejected_writes: int
    validation_passed: bool


@dataclass(slots=True)
class _EpochSessionState:
    epoch_id: int
    writer_id: str
    kernel_seq: int
    kernel_time: int
    fields_touched: set[str]
    rejected_writes: int
    paused: bool


class KernelEpoch:
    __slots__ = ("_kernel", "_audit")

    def __init__(self, kernel: "ResidentKernel") -> None:
        self._kernel = kernel
        self._audit: KernelEpochAudit | None = None

    def __enter__(self) -> "KernelEpoch":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._audit = self._kernel.end_epoch()
        return False

    @property
    def audit_record(self) -> KernelEpochAudit | None:
        return self._audit


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
    "kernel_epoch",
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
    "kernel_epoch": set(),
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
        "kernel_epoch",
    },
    "ready": _ALLOWED_GOV_FIELDS | _ALLOWED_EMB_FIELDS,
    "degraded": _ALLOWED_GOV_FIELDS | _ALLOWED_EMB_FIELDS,
    "maintenance": _ALLOWED_GOV_FIELDS | _ALLOWED_EMB_FIELDS,
    "shutdown": {
        "kernel_time",
        "kernel_seq",
        "system_phase",
        "posture_flags",
        "kernel_epoch",
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
        "kernel_epoch",
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
        kernel_epoch: int,
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
        self.kernel_epoch = kernel_epoch
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
    __slots__ = (
        "_governance",
        "_embodiment",
        "_last_checkpoint",
        "_active_epoch",
        "_checkpoint_in_progress",
        "_restore_in_progress",
        "_checkpoint_epoch_id",
    )

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
            kernel_epoch=0,
        )
        self._embodiment = _EmbodimentState(
            sensor_presence_flags={key: False for key in _ALLOWED_SENSORS},
            sensor_health_flags={key: False for key in _ALLOWED_SENSORS},
            actuator_output_state={key: False for key in _ALLOWED_ACTUATORS},
            delta_signals={key: 0 for key in _ALLOWED_DELTAS},
            kernel_seq=0,
            kernel_time=0,
        )
        self._last_checkpoint: KernelCheckpoint | None = None
        self._active_epoch: _EpochSessionState | None = None
        self._checkpoint_in_progress = False
        self._restore_in_progress = False
        self._checkpoint_epoch_id: int | None = None

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
            kernel_epoch=self._governance.kernel_epoch,
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

    def get_recent_silhouettes(self, n: int = 7) -> list[Dict[str, object]]:
        """Return recent embodiment silhouette artifacts without mutating kernel state."""
        return load_recent_silhouettes(n)

    def update_governance(self, writer_id: str, **changes: object) -> None:
        self._ensure_epoch_active()
        try:
            self._reject_unknown_fields(changes, _ALLOWED_GOV_FIELDS)
            self._reject_unauthorized(writer_id, changes, _GOV_FIELD_WRITERS)
            self._reject_phase_mismatch(changes)
            validated = self._validate_governance_updates(changes)
        except (KernelMisuseError, KernelUnauthorizedError, KernelInvariantError):
            self._note_epoch_rejection()
            raise
        if validated:
            self._governance._apply(_UPDATE_TOKEN, **validated)
            self._track_epoch_fields(validated.keys())

    def update_embodiment(self, writer_id: str, **changes: object) -> None:
        self._ensure_epoch_active()
        try:
            self._reject_unknown_fields(changes, _ALLOWED_EMB_FIELDS)
            self._reject_unauthorized(writer_id, changes, _EMB_FIELD_WRITERS)
            self._reject_phase_mismatch(changes)
            validated = self._validate_embodiment_updates(changes)
        except (KernelMisuseError, KernelUnauthorizedError, KernelInvariantError):
            self._note_epoch_rejection()
            raise
        if validated:
            self._embodiment._apply(_UPDATE_TOKEN, **validated)
            self._track_epoch_fields(validated.keys())

    def begin_epoch(self, writer_id: str) -> KernelEpoch:
        if self._active_epoch is not None:
            raise KernelMisuseError("Epoch session already active")
        if not isinstance(writer_id, str) or not writer_id:
            raise KernelMisuseError("Epoch writer_id must be a non-empty string")
        epoch_id = self._governance.kernel_epoch + 1
        self._active_epoch = _EpochSessionState(
            epoch_id=epoch_id,
            writer_id=writer_id,
            kernel_seq=self._embodiment.kernel_seq,
            kernel_time=self._embodiment.kernel_time,
            fields_touched=set(),
            rejected_writes=0,
            paused=False,
        )
        self._checkpoint_epoch_id = None
        return KernelEpoch(self)

    def epoch_active(self) -> bool:
        """Return True when an unpaused epoch session is active."""
        return self._active_epoch is not None and not self._active_epoch.paused

    def active_epoch_id(self) -> int | None:
        """Return the currently active epoch id, if any."""
        if self._active_epoch is None:
            return None
        return self._active_epoch.epoch_id

    def end_epoch(self) -> KernelEpochAudit:
        if self._active_epoch is None:
            raise KernelMisuseError("No active epoch session to end")
        session = self._active_epoch
        self._governance._apply(_UPDATE_TOKEN, kernel_epoch=session.epoch_id)
        self._active_epoch = None
        fields = tuple(sorted(session.fields_touched))
        return KernelEpochAudit(
            epoch_id=session.epoch_id,
            writer_id=session.writer_id,
            kernel_seq=session.kernel_seq,
            kernel_time=session.kernel_time,
            fields_touched=fields,
            rejected_writes=session.rejected_writes,
            validation_passed=session.rejected_writes == 0,
        )

    def pause_epoch(self) -> None:
        self._ensure_epoch_active()
        self._active_epoch.paused = True

    def resume_epoch(self) -> None:
        self._ensure_epoch_active()
        self._active_epoch.paused = False

    def create_checkpoint(self, *, force: bool = False) -> KernelCheckpoint:
        self._ensure_epoch_active()
        if self._checkpoint_in_progress or self._restore_in_progress:
            self._log_audit_warning(
                "checkpoint contention detected",
                action="create_checkpoint",
                epoch_id=self._active_epoch.epoch_id,
                in_progress=self._checkpoint_in_progress,
                restore_in_progress=self._restore_in_progress,
            )
            raise KernelMisuseError("Checkpoint already in progress")
        if self._checkpoint_epoch_id == self._active_epoch.epoch_id and not force:
            self._log_audit_warning(
                "duplicate checkpoint attempt blocked",
                action="create_checkpoint",
                epoch_id=self._active_epoch.epoch_id,
            )
            raise KernelMisuseError("Checkpoint already recorded for this epoch")
        if self._checkpoint_epoch_id == self._active_epoch.epoch_id and force:
            self._log_audit_warning(
                "forced checkpoint override",
                action="create_checkpoint",
                epoch_id=self._active_epoch.epoch_id,
            )
        self._checkpoint_in_progress = True
        self._checkpoint_epoch_id = self._active_epoch.epoch_id
        try:
            governance = {
                "identity_invariants": self._governance.identity_invariants,
                "doctrine_digest": self._governance.doctrine_digest,
                "active_policy_pointer": self._governance.active_policy_pointer,
                "authority_flags": dict(self._governance.authority_flags),
                "system_phase": self._governance.system_phase,
                "posture_flags": self._governance.posture_flags,
                "constraint_rejustify_deadline": self._governance.constraint_rejustify_deadline,
                "last_justification_at": self._governance.last_justification_at,
                "federation_compat_digest": dict(self._governance.federation_compat_digest),
                "kernel_epoch": self._governance.kernel_epoch,
            }
            embodiment = {
                "sensor_presence_flags": dict(self._embodiment.sensor_presence_flags),
                "sensor_health_flags": dict(self._embodiment.sensor_health_flags),
                "actuator_output_state": dict(self._embodiment.actuator_output_state),
                "delta_signals": dict(self._embodiment.delta_signals),
                "kernel_seq": self._embodiment.kernel_seq,
                "kernel_time": self._embodiment.kernel_time,
            }
            digest = self._hash_checkpoint_payload(
                _KERNEL_VERSION,
                governance,
                embodiment,
            )
            checkpoint = KernelCheckpoint(
                version=_KERNEL_VERSION,
                governance=self._freeze_mapping(governance),
                embodiment=self._freeze_mapping(embodiment),
                digest=digest,
            )
            self._last_checkpoint = checkpoint
            return checkpoint
        finally:
            self._checkpoint_in_progress = False

    def restore_checkpoint(
        self,
        checkpoint: KernelCheckpoint | Mapping[str, object],
        *,
        force: bool = False,
    ) -> None:
        if self._checkpoint_in_progress or self._restore_in_progress:
            self._log_audit_warning(
                "restore contention detected",
                action="restore_checkpoint",
                epoch_id=self._active_epoch.epoch_id if self._active_epoch else None,
                checkpoint_in_progress=self._checkpoint_in_progress,
                restore_in_progress=self._restore_in_progress,
            )
            raise KernelMisuseError("Restore already in progress")
        session = self._active_epoch
        if session is not None:
            has_updates = bool(session.fields_touched) or session.rejected_writes > 0
            if not session.paused and not force:
                self._log_audit_warning(
                    "restore blocked during active epoch",
                    action="restore_checkpoint",
                    epoch_id=session.epoch_id,
                    has_updates=has_updates,
                )
                raise KernelMisuseError("Restore requires paused or inactive epoch")
            if has_updates and not force:
                self._log_audit_warning(
                    "restore blocked with queued updates",
                    action="restore_checkpoint",
                    epoch_id=session.epoch_id,
                    fields_touched=tuple(sorted(session.fields_touched)),
                )
                raise KernelMisuseError("Restore blocked with queued updates")
            if not session.paused and force:
                self._log_audit_warning(
                    "forced restore mid-tick",
                    action="restore_checkpoint",
                    epoch_id=session.epoch_id,
                    has_updates=has_updates,
                )
            if has_updates and force:
                self._log_audit_warning(
                    "forced restore with queued updates",
                    action="restore_checkpoint",
                    epoch_id=session.epoch_id,
                    fields_touched=tuple(sorted(session.fields_touched)),
                )
        self._restore_in_progress = True
        try:
            payload = self._coerce_checkpoint_payload(checkpoint)
            expected_digest = self._hash_checkpoint_payload(
                payload["version"],
                payload["governance"],
                payload["embodiment"],
            )
            if expected_digest != payload["digest"]:
                raise KernelInvariantError("Checkpoint digest mismatch")
            if payload["version"] != _KERNEL_VERSION:
                raise KernelInvariantError("Checkpoint version mismatch")
            validated_governance, validated_embodiment = self._validate_checkpoint_payload(
                payload["governance"],
                payload["embodiment"],
            )
            self._validate_restore_epoch(validated_governance["kernel_epoch"])
        except KernelInvariantError as exc:
            self._note_epoch_rejection()
            self._force_safe_posture()
            self._log_audit_alert(
                "restore validation failed",
                action="restore_checkpoint",
                error=str(exc),
                epoch_id=self._active_epoch.epoch_id if self._active_epoch else None,
            )
            raise
        finally:
            self._restore_in_progress = False
        self._governance._apply(_UPDATE_TOKEN, **validated_governance)
        self._embodiment._apply(_UPDATE_TOKEN, **validated_embodiment)
        self._track_epoch_fields(
            tuple(validated_governance.keys()) + tuple(validated_embodiment.keys())
        )
        digest = self._hash_checkpoint_payload(
            _KERNEL_VERSION,
            validated_governance,
            validated_embodiment,
        )
        self._last_checkpoint = KernelCheckpoint(
            version=_KERNEL_VERSION,
            governance=self._freeze_mapping(validated_governance),
            embodiment=self._freeze_mapping(validated_embodiment),
            digest=digest,
        )

    def detect_corruption(self) -> None:
        if self._active_epoch is not None:
            raise KernelMisuseError("Cannot detect corruption during an active epoch")
        checkpoint = self._last_checkpoint
        if checkpoint is None:
            raise KernelMisuseError("No checkpoint available for corruption detection")
        governance = checkpoint.governance
        embodiment = checkpoint.embodiment
        current_epoch = self._governance.kernel_epoch
        prior_epoch = governance["kernel_epoch"]
        if current_epoch < prior_epoch:
            raise KernelCorruptionError("kernel_epoch regressed")
        if current_epoch > prior_epoch + 1:
            raise KernelCorruptionError("kernel_epoch jump detected")
        if current_epoch == prior_epoch:
            if not self._checkpoint_state_matches(governance, embodiment):
                raise KernelCorruptionError("writes without epoch evidence detected")
        if self._governance.identity_invariants != governance["identity_invariants"]:
            raise KernelCorruptionError("identity_invariants drift detected")
        current_phase = self._governance.system_phase
        prior_phase = governance["system_phase"]
        if current_phase != prior_phase:
            allowed = _ALLOWED_PHASE_TRANSITIONS.get(prior_phase, set())
            if current_phase not in allowed:
                raise KernelCorruptionError(
                    f"Illegal phase transition: {prior_phase} -> {current_phase}"
                )
        monotonic_pairs = [
            ("kernel_seq", self._embodiment.kernel_seq, embodiment["kernel_seq"]),
            ("kernel_time", self._embodiment.kernel_time, embodiment["kernel_time"]),
            (
                "last_justification_at",
                self._governance.last_justification_at,
                governance["last_justification_at"],
            ),
            (
                "constraint_rejustify_deadline",
                self._governance.constraint_rejustify_deadline,
                governance["constraint_rejustify_deadline"],
            ),
        ]
        for field, current, prior in monotonic_pairs:
            if current < prior:
                raise KernelCorruptionError(f"{field} regressed")
        for key, prior in embodiment["delta_signals"].items():
            current = self._embodiment.delta_signals.get(key, 0)
            if current < prior:
                raise KernelCorruptionError("delta_signals regressed")

    def _coerce_checkpoint_payload(
        self, checkpoint: KernelCheckpoint | Mapping[str, object]
    ) -> Dict[str, object]:
        if isinstance(checkpoint, KernelCheckpoint):
            version = checkpoint.version
            governance = self._defrost_mapping(checkpoint.governance)
            embodiment = self._defrost_mapping(checkpoint.embodiment)
            digest = checkpoint.digest
        elif isinstance(checkpoint, Mapping):
            try:
                version = checkpoint["version"]
                governance = self._defrost_mapping(checkpoint["governance"])
                embodiment = self._defrost_mapping(checkpoint["embodiment"])
                digest = checkpoint["digest"]
            except KeyError as exc:
                raise KernelInvariantError("Checkpoint missing required fields") from exc
        else:
            raise KernelInvariantError("Checkpoint must be a KernelCheckpoint or mapping")
        if not isinstance(digest, str) or not digest:
            raise KernelInvariantError("Checkpoint digest must be a non-empty string")
        if not isinstance(version, str) or not version:
            raise KernelInvariantError("Checkpoint version must be a non-empty string")
        return {
            "version": version,
            "governance": governance,
            "embodiment": embodiment,
            "digest": digest,
        }

    def _validate_checkpoint_payload(
        self,
        governance: Mapping[str, object],
        embodiment: Mapping[str, object],
    ) -> Tuple[Dict[str, object], Dict[str, object]]:
        self._reject_unknown_fields(governance, _ALLOWED_GOV_FIELDS)
        self._reject_unknown_fields(embodiment, _ALLOWED_EMB_FIELDS)
        policy_pointer = self._validate_policy_pointer(governance["active_policy_pointer"])
        last_justification_at = self._validate_monotonic_int(
            governance["last_justification_at"],
            0,
            "last_justification_at",
        )
        validated_governance = {
            "identity_invariants": self._validate_identity_invariants(
                governance["identity_invariants"]
            ),
            "doctrine_digest": self._validate_digest(
                governance["doctrine_digest"],
                "doctrine_digest",
            ),
            "active_policy_pointer": policy_pointer,
            "authority_flags": self._validate_checkpoint_authority_flags(
                governance["authority_flags"],
                policy_pointer,
            ),
            "system_phase": self._validate_phase_value(governance["system_phase"]),
            "posture_flags": self._validate_posture_flags(governance["posture_flags"]),
            "constraint_rejustify_deadline": self._validate_checkpoint_deadline(
                governance["constraint_rejustify_deadline"],
                last_justification_at,
            ),
            "last_justification_at": last_justification_at,
            "federation_compat_digest": self._validate_federation_digest(
                governance["federation_compat_digest"]
            ),
            "kernel_epoch": self._validate_epoch_value(governance["kernel_epoch"]),
        }
        validated_embodiment = {
            "sensor_presence_flags": self._validate_bool_map(
                embodiment["sensor_presence_flags"],
                _ALLOWED_SENSORS,
                "sensor_presence_flags",
            ),
            "sensor_health_flags": self._validate_bool_map(
                embodiment["sensor_health_flags"],
                _ALLOWED_SENSORS,
                "sensor_health_flags",
            ),
            "actuator_output_state": self._validate_bool_map(
                embodiment["actuator_output_state"],
                _ALLOWED_ACTUATORS,
                "actuator_output_state",
            ),
            "delta_signals": self._validate_counter_map(
                embodiment["delta_signals"],
                _ALLOWED_DELTAS,
                "delta_signals",
                {key: 0 for key in _ALLOWED_DELTAS},
            ),
            "kernel_seq": self._validate_monotonic_int(
                embodiment["kernel_seq"],
                0,
                "kernel_seq",
            ),
            "kernel_time": self._validate_monotonic_int(
                embodiment["kernel_time"],
                0,
                "kernel_time",
            ),
        }
        self._validate_checkpoint_sensor_health(
            validated_embodiment["sensor_presence_flags"],
            validated_embodiment["sensor_health_flags"],
        )
        self._validate_checkpoint_actuator_state(
            validated_embodiment["actuator_output_state"],
            validated_governance["system_phase"],
        )
        return validated_governance, validated_embodiment

    def _force_safe_posture(self) -> None:
        self._governance._apply(_UPDATE_TOKEN, posture_flags="safe_brownout")
        self._track_epoch_fields(("posture_flags",))

    def _validate_checkpoint_authority_flags(
        self, value: object, policy_pointer: Tuple[str, int]
    ) -> Dict[str, bool]:
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
        if value["automated_ok"] and policy_pointer == ("", 0):
            raise KernelInvariantError("automated_ok requires active_policy_pointer")
        return {key: value[key] for key in required}

    def _validate_checkpoint_deadline(self, value: object, last: int) -> int:
        if not isinstance(value, int) or value < 0:
            raise KernelInvariantError("constraint_rejustify_deadline must be int")
        if value < last:
            raise KernelInvariantError("deadline must be >= last_justification_at")
        return value

    def _validate_checkpoint_sensor_health(
        self,
        presence: Mapping[str, bool],
        health: Mapping[str, bool],
    ) -> None:
        for key, is_healthy in health.items():
            if is_healthy and not presence.get(key, False):
                raise KernelInvariantError("sensor health requires presence")

    def _validate_checkpoint_actuator_state(
        self,
        state: Mapping[str, bool],
        phase: str,
    ) -> None:
        if phase not in {"ready", "degraded"}:
            if any(state.values()):
                raise KernelInvariantError("actuator outputs require ready/degraded")

    def _validate_phase_value(self, value: object) -> str:
        if not isinstance(value, str) or value not in _ALLOWED_PHASES:
            raise KernelInvariantError("system_phase must be a known phase")
        return value

    def _validate_epoch_value(self, value: object) -> int:
        if not isinstance(value, int) or value < 0:
            raise KernelInvariantError("kernel_epoch must be a non-negative int")
        return value

    def _freeze_mapping(self, data: Mapping[str, object]) -> Mapping[str, object]:
        frozen: Dict[str, object] = {}
        for key, value in data.items():
            if isinstance(value, Mapping):
                frozen[key] = MappingProxyType(dict(value))
            elif isinstance(value, tuple):
                frozen[key] = tuple(value)
            else:
                frozen[key] = value
        return MappingProxyType(frozen)

    def _defrost_mapping(self, data: object) -> Dict[str, object]:
        if not isinstance(data, Mapping):
            raise KernelInvariantError("Checkpoint sections must be mappings")
        defrosted: Dict[str, object] = {}
        for key, value in data.items():
            if isinstance(value, Mapping):
                defrosted[key] = dict(value)
            else:
                defrosted[key] = value
        return defrosted

    def _hash_checkpoint_payload(
        self,
        version: str,
        governance: Mapping[str, object],
        embodiment: Mapping[str, object],
    ) -> str:
        payload = {
            "version": version,
            "governance": self._normalize_for_hash(governance),
            "embodiment": self._normalize_for_hash(embodiment),
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _normalize_for_hash(self, value: object) -> object:
        if isinstance(value, Mapping):
            return {
                key: self._normalize_for_hash(value[key])
                for key in sorted(value)
            }
        if isinstance(value, tuple):
            return [self._normalize_for_hash(item) for item in value]
        if isinstance(value, list):
            return [self._normalize_for_hash(item) for item in value]
        return value

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

    def _ensure_epoch_active(self) -> None:
        if self._active_epoch is None:
            raise KernelWriteOutsideEpochError("Kernel mutations require an epoch")

    def _note_epoch_rejection(self) -> None:
        if self._active_epoch is not None:
            self._active_epoch.rejected_writes += 1

    def _log_audit_warning(self, message: str, **context: object) -> None:
        if context:
            _logger.warning(
                "AUDIT WARNING: %s | %s",
                message,
                json.dumps(context, sort_keys=True),
            )
        else:
            _logger.warning("AUDIT WARNING: %s", message)

    def _log_audit_alert(self, message: str, **context: object) -> None:
        if context:
            _logger.error(
                "AUDIT ALERT: %s | %s",
                message,
                json.dumps(context, sort_keys=True),
            )
        else:
            _logger.error("AUDIT ALERT: %s", message)

    def _track_epoch_fields(self, fields: Tuple[str, ...] | list[str] | set[str]) -> None:
        if self._active_epoch is not None:
            self._active_epoch.fields_touched.update(fields)

    def _checkpoint_state_matches(
        self, governance: Mapping[str, object], embodiment: Mapping[str, object]
    ) -> bool:
        current_governance = {
            "identity_invariants": self._governance.identity_invariants,
            "doctrine_digest": self._governance.doctrine_digest,
            "active_policy_pointer": self._governance.active_policy_pointer,
            "authority_flags": dict(self._governance.authority_flags),
            "system_phase": self._governance.system_phase,
            "posture_flags": self._governance.posture_flags,
            "constraint_rejustify_deadline": self._governance.constraint_rejustify_deadline,
            "last_justification_at": self._governance.last_justification_at,
            "federation_compat_digest": dict(self._governance.federation_compat_digest),
            "kernel_epoch": self._governance.kernel_epoch,
        }
        current_embodiment = {
            "sensor_presence_flags": dict(self._embodiment.sensor_presence_flags),
            "sensor_health_flags": dict(self._embodiment.sensor_health_flags),
            "actuator_output_state": dict(self._embodiment.actuator_output_state),
            "delta_signals": dict(self._embodiment.delta_signals),
            "kernel_seq": self._embodiment.kernel_seq,
            "kernel_time": self._embodiment.kernel_time,
        }
        return current_governance == dict(governance) and current_embodiment == dict(
            embodiment
        )

    def _validate_restore_epoch(self, checkpoint_epoch: int) -> None:
        if checkpoint_epoch < self._governance.kernel_epoch:
            raise KernelInvariantError("checkpoint epoch regressed")


__all__ = [
    "EmbodimentView",
    "GovernanceView",
    "KernelCheckpoint",
    "KernelCorruptionError",
    "KernelInvariantError",
    "KernelMisuseError",
    "KernelWriteOutsideEpochError",
    "KernelUnauthorizedError",
    "KernelEpoch",
    "KernelEpochAudit",
    "ResidentKernel",
]
