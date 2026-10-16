"""Cognitive layer surface for proposal-only inference."""

from typing import Dict, Mapping

from .surface import (
    CognitiveCache,
    CognitiveProposal,
    CognitiveSurface,
    CognitiveViolation,
    IntentBundleDraft,
    PreferenceInference,
)
from .goal_selection import GoalSelectionKernel, KernelProposal


def run_cognitive_cycle(context: Mapping[str, object]) -> Dict[str, object]:
    """Run the canonical cognitive cycle through a lazy integration import.

    Keeping the compatibility facade lazy avoids a package initialization cycle:
    governance imports the cognitive surface, while the integration facade
    itself imports governance helpers.
    """
    from .integration import run_cognitive_cycle as _run_cognitive_cycle

    return _run_cognitive_cycle(context)


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
