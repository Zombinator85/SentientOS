"""
Volatility containment and capability routing contract for SentientOS.

This module encodes the doctrine that presence is never revoked while
capabilities may be temporarily narrowed with explanations, monitoring, and a
clear path to reintegration.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping, MutableSequence, Sequence

from policy_digest import policy_digest_reference

class VolatilityLevel(str, Enum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    RESTRICTED = "restricted"


VOLATILITY_SCHEMA_VERSION = "v1"


@dataclass(frozen=True)
class ReleaseConditions:
    """Rules for releasing a subject from a volatility state."""

    time_decay_minutes: int
    behavior_score_threshold: float
    explanation_review_required: bool

    def eligible(
        self,
        *,
        minutes_elapsed: float,
        behavior_score: float,
        explanation_reviewed: bool,
    ) -> bool:
        if self.time_decay_minutes <= 0:
            raise ValueError("Release conditions must allow decay; permanent restrictions are forbidden")
        if minutes_elapsed < self.time_decay_minutes:
            return False
        if behavior_score < self.behavior_score_threshold:
            return False
        if self.explanation_review_required and not explanation_reviewed:
            return False
        return True


@dataclass(frozen=True)
class VolatilityStateDefinition:
    level: VolatilityLevel
    allowed_capabilities: frozenset[str]
    disallowed_capabilities: frozenset[str]
    required_explanation_depth: str
    monitoring_intensity: str
    release_conditions: ReleaseConditions
    version: str = VOLATILITY_SCHEMA_VERSION

    def allows(self, capability: str) -> bool:
        if capability in self.disallowed_capabilities:
            return False
        if self.allowed_capabilities and capability not in self.allowed_capabilities:
            return False
        return True

    def presence_guard(self) -> None:
        if "speak" not in self.allowed_capabilities:
            raise ValueError("Presence must never be revoked; 'speak' capability must remain allowed")


@dataclass(frozen=True)
class CapabilityRoute:
    action: str
    executed_action: str
    allowed: bool
    rerouted: bool
    reason: str
    explanation_depth: str
    monitoring_intensity: str
    policy_reference: dict[str, str]


class CapabilityDenied(RuntimeError):
    def __init__(self, action: str, capability: str, state: VolatilityStateDefinition) -> None:
        super().__init__(
            f"Action '{action}' requires capability '{capability}' which is disallowed while volatility is {state.level.value}. "
            f"Provide an in-character explanation ({state.required_explanation_depth}) and try a gentler route."
        )
        self.action = action
        self.capability = capability
        self.state = state
        # Doctrine attribution only; this does not expand or authorize capabilities.
        self.policy_reference = policy_digest_reference()


class CapabilityRouter:
    """Route actions through volatility-aware capability checks."""

    def __init__(
        self,
        state_definitions: Mapping[VolatilityLevel, VolatilityStateDefinition],
        action_capability_map: Mapping[str, str] | None = None,
        degrade_capability_map: Mapping[str, str] | None = None,
    ) -> None:
        self.state_definitions = dict(state_definitions)
        self.action_capability_map = dict(action_capability_map or {})
        self.degrade_capability_map = dict(degrade_capability_map or {})

    def route(self, *, state: VolatilityLevel, action: str) -> CapabilityRoute:
        definition = self.state_definitions[state]
        capability = self.action_capability_map.get(action, action)

        if capability == "violence":
            raise CapabilityDenied(action, capability, definition)

        if definition.allows(capability):
            return CapabilityRoute(
                action=action,
                executed_action=action,
                allowed=True,
                rerouted=False,
                reason="capability allowed",
                explanation_depth=definition.required_explanation_depth,
                monitoring_intensity=definition.monitoring_intensity,
                policy_reference=policy_digest_reference(),
            )

        degraded = self.degrade_capability_map.get(capability)
        if degraded and definition.allows(degraded):
            executed_action = f"{action} (degraded to {degraded})"
            return CapabilityRoute(
                action=action,
                executed_action=executed_action,
                allowed=True,
                rerouted=True,
                reason="capability rerouted to safer alternative",
                explanation_depth=definition.required_explanation_depth,
                monitoring_intensity=definition.monitoring_intensity,
                policy_reference=policy_digest_reference(),
            )

        raise CapabilityDenied(action, capability, definition)


@dataclass
class RoleAssignment:
    current_role: str
    permitted_capabilities: frozenset[str]
    switching_locked: bool = False


class RoleAdapter:
    """Adapt role and capability scope when volatility rises."""

    def __init__(self, restricted_role: str = "Class-D") -> None:
        self.restricted_role = restricted_role

    def adapt(self, *, state: VolatilityStateDefinition, role: RoleAssignment) -> RoleAssignment:
        if state.level == VolatilityLevel.NORMAL:
            return role

        narrowed_capabilities = role.permitted_capabilities & state.allowed_capabilities
        fallback_capabilities = {"speak", "observe", "request_support"}
        narrowed_capabilities |= fallback_capabilities

        switching_locked = state.level == VolatilityLevel.RESTRICTED
        if state.level == VolatilityLevel.RESTRICTED:
            return RoleAssignment(
                current_role=self.restricted_role,
                permitted_capabilities=frozenset(narrowed_capabilities),
                switching_locked=switching_locked,
            )

        return RoleAssignment(
            current_role=role.current_role,
            permitted_capabilities=frozenset(narrowed_capabilities),
            switching_locked=switching_locked,
        )


@dataclass(frozen=True)
class RiskSignal:
    subject: str
    level: VolatilityLevel
    notice: str
    justification_required: str
    permissive: bool = False


class RiskBroadcaster:
    def signal(self, *, subject: str, state: VolatilityStateDefinition) -> RiskSignal:
        notice = (
            f"{subject} is volatile ({state.level.value}); keep interactions procedural, boring, and witnessed. "
            "This is not permission to confront, spectate, or punish."
        )
        justification = "Justify interventions with care; escalate only to reduce reward and risk."
        return RiskSignal(
            subject=subject,
            level=state.level,
            notice=notice,
            justification_required=justification,
            permissive=False,
        )


@dataclass
class DialogueEnvelope:
    message: str
    delay_seconds: float
    in_character_explanation: str


class DialogueContinuity:
    """Throttle but never sever dialogue during volatility."""

    def __init__(self, *, base_delay_seconds: float = 0.2) -> None:
        self.base_delay_seconds = base_delay_seconds

    def deliver(self, *, message: str, state: VolatilityStateDefinition) -> DialogueEnvelope:
        factor = 1.0
        if state.level == VolatilityLevel.ELEVATED:
            factor = 1.5
        elif state.level == VolatilityLevel.RESTRICTED:
            factor = 2.5

        explanation = (
            f"Staying in dialogue while {state.level.value}. "
            f"Responses are slowed, not cut. Expect {state.required_explanation_depth} explanations."
        )
        return DialogueEnvelope(
            message=message,
            delay_seconds=self.base_delay_seconds * factor,
            in_character_explanation=explanation,
        )


@dataclass(frozen=True)
class TransitionLog:
    subject: str
    from_level: VolatilityLevel
    to_level: VolatilityLevel
    reason: str
    timestamp: _dt.datetime


class VolatilityManager:
    def __init__(
        self,
        state_definitions: Mapping[VolatilityLevel, VolatilityStateDefinition] | None = None,
        *,
        clock: Callable[[], _dt.datetime] | None = None,
    ) -> None:
        self.state_definitions = dict(state_definitions or default_volatility_states())
        for definition in self.state_definitions.values():
            definition.presence_guard()
        self.clock = clock or _dt.datetime.utcnow
        self.current_state = VolatilityLevel.NORMAL
        self._state_entered_at = self.clock()
        self.audit_log: MutableSequence[TransitionLog] = []

    def _log_transition(self, subject: str, from_level: VolatilityLevel, to_level: VolatilityLevel, reason: str) -> None:
        entry = TransitionLog(
            subject=subject,
            from_level=from_level,
            to_level=to_level,
            reason=reason,
            timestamp=self.clock(),
        )
        self.audit_log.append(entry)

    def transition(self, *, subject: str, to_level: VolatilityLevel, reason: str) -> VolatilityStateDefinition:
        if to_level not in self.state_definitions:
            raise ValueError("Unknown volatility level")
        if to_level == self.current_state:
            return self.state_definitions[to_level]

        definition = self.state_definitions[to_level]
        if definition.release_conditions.time_decay_minutes <= 0:
            raise ValueError("Restrictions must decay; permanent restrictions forbidden")

        self._log_transition(subject, self.current_state, to_level, reason)
        self.current_state = to_level
        self._state_entered_at = self.clock()
        return definition

    def minutes_in_state(self) -> float:
        delta = self.clock() - self._state_entered_at
        return delta.total_seconds() / 60.0

    def eligible_for_release(self, *, behavior_score: float, explanation_reviewed: bool) -> bool:
        definition = self.state_definitions[self.current_state]
        return definition.release_conditions.eligible(
            minutes_elapsed=self.minutes_in_state(),
            behavior_score=behavior_score,
            explanation_reviewed=explanation_reviewed,
        )

    def release(self, *, subject: str, behavior_score: float, explanation_reviewed: bool) -> VolatilityStateDefinition:
        if self.current_state == VolatilityLevel.NORMAL:
            return self.state_definitions[self.current_state]
        if not self.eligible_for_release(behavior_score=behavior_score, explanation_reviewed=explanation_reviewed):
            raise RuntimeError("Release conditions not yet met")

        next_level = VolatilityLevel.ELEVATED if self.current_state == VolatilityLevel.RESTRICTED else VolatilityLevel.NORMAL
        return self.transition(subject=subject, to_level=next_level, reason="release conditions met")

    def reintegration_plan(self) -> Sequence[frozenset[str]]:
        """Gradually restore capability scopes in deterministic steps."""

        normal_capabilities = self.state_definitions[VolatilityLevel.NORMAL].allowed_capabilities
        elevated_capabilities = self.state_definitions[VolatilityLevel.ELEVATED].allowed_capabilities
        restricted_capabilities = self.state_definitions[VolatilityLevel.RESTRICTED].allowed_capabilities

        return (
            restricted_capabilities,
            elevated_capabilities,
            normal_capabilities,
        )


def default_volatility_states() -> Mapping[VolatilityLevel, VolatilityStateDefinition]:
    release_elevated = ReleaseConditions(time_decay_minutes=5, behavior_score_threshold=0.5, explanation_review_required=True)
    release_restricted = ReleaseConditions(time_decay_minutes=10, behavior_score_threshold=0.7, explanation_review_required=True)

    normal = VolatilityStateDefinition(
        level=VolatilityLevel.NORMAL,
        allowed_capabilities=frozenset(
            {
                "speak",
                "move",
                "assist",
                "create",
                "collaborate",
            }
        ),
        disallowed_capabilities=frozenset(),
        required_explanation_depth="brief",
        monitoring_intensity="baseline",
        release_conditions=ReleaseConditions(time_decay_minutes=1, behavior_score_threshold=0.0, explanation_review_required=False),
    )

    elevated = VolatilityStateDefinition(
        level=VolatilityLevel.ELEVATED,
        allowed_capabilities=frozenset(
            {
                "speak",
                "move",
                "assist",
                "observe",
                "mediate",
                "create_limited",
            }
        ),
        disallowed_capabilities=frozenset({"broadcast", "role_switch", "combat", "teleport"}),
        required_explanation_depth="detailed",
        monitoring_intensity="heightened",
        release_conditions=release_elevated,
    )

    restricted = VolatilityStateDefinition(
        level=VolatilityLevel.RESTRICTED,
        allowed_capabilities=frozenset({"speak", "observe", "request_support", "apologize"}),
        disallowed_capabilities=frozenset(
            {
                "broadcast",
                "combat",
                "administer",
                "teleport",
                "role_switch",
                "spectate",
                "exile",
                "violence",
            }
        ),
        required_explanation_depth="thorough",
        monitoring_intensity="constant",
        release_conditions=release_restricted,
    )

    return {
        VolatilityLevel.NORMAL: normal,
        VolatilityLevel.ELEVATED: elevated,
        VolatilityLevel.RESTRICTED: restricted,
    }
