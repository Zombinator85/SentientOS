"""Integrity utilities for alignment-contract enforcement."""

from .covenant_autoalign import (
    autoalign_after_amendment,
    autoalign_before_cycle,
    autoalign_on_boot,
)
from .explanation_integrity import (
    ExplanationArtifact,
    ExplanationContractViolation,
    ExplanationIntegrityError,
    ExplanationInputs,
    build_explanation_artifact,
    build_explanation_with_fallback,
    validate_explanation_artifact,
)

__all__ = [
    "autoalign_after_amendment",
    "autoalign_before_cycle",
    "autoalign_on_boot",
    "ExplanationArtifact",
    "ExplanationContractViolation",
    "ExplanationIntegrityError",
    "ExplanationInputs",
    "build_explanation_artifact",
    "build_explanation_with_fallback",
    "validate_explanation_artifact",
]
