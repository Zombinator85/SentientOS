"""Unregistered proposal for separately admitted calibration review.

This definition is deliberately absent from AUTHORITY_DEFINITIONS until the
repository's operator-approved registration workflow accepts its exact digest.
"""
from __future__ import annotations

from .codex_task_authority_admission import TaskAuthorityDefinition

RESIDENT_EPISTEMIC_CALIBRATION_REVIEW = "resident_epistemic_calibration_review"
RESIDENT_EPISTEMIC_CALIBRATION_REVIEW_PRINCIPAL = (
    "deterministic_resident_epistemic_calibration_controller")
CALIBRATION_REVIEW_EFFECTS = tuple(sorted({
    "exact_epistemic_calibration_record_read",
    "exact_epistemic_forecast_state_read",
    "exact_epistemic_outcome_binding_read",
    "deterministic_calibration_evidence_consistency_validation",
    "bounded_calibration_update_candidate_construction",
}))

RESIDENT_EPISTEMIC_CALIBRATION_REVIEW_DEFINITION = TaskAuthorityDefinition(
    capability_id=RESIDENT_EPISTEMIC_CALIBRATION_REVIEW,
    subsystem_kinds=frozenset({"epistemics"}),
    principal_kinds=frozenset({RESIDENT_EPISTEMIC_CALIBRATION_REVIEW_PRINCIPAL}),
    required_effects=frozenset(CALIBRATION_REVIEW_EFFECTS),
    required_goal_phrases=(
        "exact proposition-bound calibration event",
        "exact historical forecast state",
        "exact current outcome evidence bindings",
        "deterministic evidence-consistency validation",
        "candidate remains proposal-only",
        "separate exact calibration-review admission",
        "separate exact epistemic state-update admission",
        "model output cannot confer mutation authority",
        "later cognition consumes only a prior epistemic position",
    ),
    forbidden_goal_phrases=(
        "automatic truth adoption", "belief overwrite", "world-state overwrite",
        "model decides truth", "model self-authorization",
        "automatic confidence inflation", "automatic policy creation",
        "automatic goal creation", "automatic permission creation",
        "automatic action", "effect admission", "provider invocation",
        "network authority", "credential access", "host actuation",
    ),
    approval_requirements=(
        "operator-approved capability-definition registration",
        "exact registered calibration-review definition",
        "exact existing proposition identity and digest",
        "exact historical forecast-state identity and digest",
        "exact source-binding identities and digests",
        "calibration comparison label cannot override bound evidence relations",
        "candidate authority remains all false",
        "separate exact state-update admission remains required",
        "compare-and-swap predecessor check",
        "immutable state and update custody",
        "durable epistemic mutation receipt",
        "post-write reconstruction verification",
    ),
    purpose=(
        "Permit a bounded deterministic controller to review one exact, durable calibration event "
        "against its historical forecast state and exact proposition-bound outcome evidence, then "
        "construct a non-authoritative state-update candidate only when the calibration label agrees "
        "with that evidence. This capability does not mutate epistemic state; a distinct existing "
        "state-update admission and compare-and-swap remain mandatory. Registration grants no runtime "
        "admission, evidence is not truth, and calibration does not create authority, policy, goals, "
        "permissions, or actions."
    ),
)

REGISTRATION_TASK_NAME = (
    "register_resident_epistemic_calibration_review_definition")
