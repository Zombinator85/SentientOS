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
from .recovery import RecoveryLadderRegistry, RecoveryProofArtifact
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
    "RecoveryProofArtifact",
    "ERROR_CODE_CATALOG",
    "RECOVERY_ELIGIBILITY_REGISTRY",
    "RecoveryEligibility",
    "format_recovery_eligibility",
    "get_recovery_eligibility",
    "recovery_eligibility_registry_hash",
]
