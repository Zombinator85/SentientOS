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
]
