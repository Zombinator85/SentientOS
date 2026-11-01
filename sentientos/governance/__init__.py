from typing import TYPE_CHECKING

from .governance_reducer import GovernanceOutcome, GovernanceReducer
from .habit_inference import (
    HabitConfig,
    HabitEvidence,
    HabitInferenceEngine,
    HabitObservation,
    HabitPolicy,
    HabitProposal,
    HabitReviewAlert,
)
from .semantic_habit_class import (
    SemanticHabitClass,
    SemanticHabitClassManager,
    SemanticHabitClassProposal,
)
from .sanction_engine import AgentStatus, SanctionEngine
from .governance_cooldown import CooldownRecord, GovernanceCooldown

if TYPE_CHECKING:
    from .intentional_forgetting import (
        ForgetDiff,
        IntentionalForgetRequest,
        IntentionalForgetResult,
        IntentionalForgettingService,
        InvariantViolation,
    )


_INTENTIONAL_FORGETTING_EXPORTS = {
    "ForgetDiff",
    "IntentionalForgetRequest",
    "IntentionalForgetResult",
    "IntentionalForgettingService",
    "InvariantViolation",
}


def __getattr__(name: str) -> object:
    if name not in _INTENTIONAL_FORGETTING_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from . import intentional_forgetting

    return getattr(intentional_forgetting, name)

__all__ = [
    "AgentStatus",
    "SanctionEngine",
    "GovernanceReducer",
    "GovernanceOutcome",
    "GovernanceCooldown",
    "CooldownRecord",
    "HabitConfig",
    "HabitEvidence",
    "HabitInferenceEngine",
    "HabitObservation",
    "HabitPolicy",
    "HabitProposal",
    "HabitReviewAlert",
    "SemanticHabitClass",
    "SemanticHabitClassManager",
    "SemanticHabitClassProposal",
    "ForgetDiff",
    "IntentionalForgetRequest",
    "IntentionalForgetResult",
    "IntentionalForgettingService",
    "InvariantViolation",
]
