"""Diagnostic error framing and recovery readiness primitives."""

from __future__ import annotations

from .error_frame import (
    DiagnosticError,
    DiagnosticErrorFrame,
    ErrorClass,
    FailedPhase,
    LogicalClock,
    build_error_frame,
    frame_exception,
    persist_error_frame,
)
from .recovery import (
    RECOVERY_FAILED,
    RECOVERY_SKIPPED,
    RECOVERY_SUCCEEDED,
    RecoveryLadderRegistry,
    RecoveryOutcome,
    RecoveryProofArtifact,
    attempt_recovery,
    persist_recovery_proof,
)
from .recovery_eligibility import (
    ERROR_CODE_CATALOG,
    RECOVERY_ELIGIBILITY_REGISTRY,
    RecoveryEligibility,
    format_recovery_eligibility,
    get_recovery_eligibility,
    registry_hash as recovery_eligibility_registry_hash,
)

__all__ = [
    "DiagnosticError",
    "DiagnosticErrorFrame",
    "ErrorClass",
    "FailedPhase",
    "LogicalClock",
    "build_error_frame",
    "frame_exception",
    "persist_error_frame",
    "RecoveryLadderRegistry",
    "RecoveryOutcome",
    "RecoveryProofArtifact",
    "RECOVERY_FAILED",
    "RECOVERY_SKIPPED",
    "RECOVERY_SUCCEEDED",
    "attempt_recovery",
    "persist_recovery_proof",
    "ERROR_CODE_CATALOG",
    "RECOVERY_ELIGIBILITY_REGISTRY",
    "RecoveryEligibility",
    "format_recovery_eligibility",
    "get_recovery_eligibility",
    "recovery_eligibility_registry_hash",
]
