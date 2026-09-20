"""Cognitive layer surface for proposal-only inference."""

from .surface import (
    CognitiveCache,
    CognitiveProposal,
    CognitiveSurface,
    CognitiveViolation,
    IntentBundleDraft,
    PreferenceInference,
)
from .goal_selection import GoalSelectionKernel, KernelProposal
from .integration import run_cognitive_cycle

__all__ = [
    "CognitiveCache",
    "CognitiveProposal",
    "CognitiveSurface",
    "CognitiveViolation",
    "GoalSelectionKernel",
    "IntentBundleDraft",
    "KernelProposal",
    "PreferenceInference",
    "run_cognitive_cycle",
]
