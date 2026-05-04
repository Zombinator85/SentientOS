from __future__ import annotations

from typing import Final

EPISTEMIC_STATUSES: Final[tuple[str, ...]] = (
    "directly_supported",
    "provisional_supported",
    "strongly_inferred",
    "plausible_but_unverified",
    "underconstrained",
    "contested",
    "contradicted_by_new_evidence",
    "superseded_by_new_evidence",
    "retracted_due_to_error",
    "policy_blocked_but_preserved",
    "quote_fidelity_failed",
    "no_new_evidence_reversal_blocked",
    "unknown",
)

SUPPORTED_EPISTEMIC_STATUSES: Final[set[str]] = {
    "directly_supported",
    "provisional_supported",
    "strongly_inferred",
}
BLOCKED_EPISTEMIC_STATUSES: Final[set[str]] = {
    "quote_fidelity_failed",
    "no_new_evidence_reversal_blocked",
}
REVISION_EPISTEMIC_STATUSES: Final[set[str]] = {
    "contradicted_by_new_evidence",
    "superseded_by_new_evidence",
    "retracted_due_to_error",
}


def normalize_epistemic_status(value: str | None) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in EPISTEMIC_STATUSES else "unknown"


def is_supported_epistemic_status(value: str | None) -> bool:
    return normalize_epistemic_status(value) in SUPPORTED_EPISTEMIC_STATUSES


def is_blocked_epistemic_status(value: str | None) -> bool:
    return normalize_epistemic_status(value) in BLOCKED_EPISTEMIC_STATUSES


def is_revision_status(value: str | None) -> bool:
    return normalize_epistemic_status(value) in REVISION_EPISTEMIC_STATUSES


def epistemic_status_ref(value: str | None) -> str:
    return f"epistemic_status:{normalize_epistemic_status(value)}"

