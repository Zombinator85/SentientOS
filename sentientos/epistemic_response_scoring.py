"""Response contract and scoring helpers for bounded epistemic evaluations.

Reason codes are exact-match outcomes only when the subject receives the same
preregistered vocabulary used by the scorer. Free-form reason labels remain
descriptive and are never converted into correctness scores after capture.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any


STANCE_VALUES = frozenset({
    "unknown", "suspended", "provisionally_supported", "supported",
    "contested", "provisionally_contradicted", "contradicted", "superseded",
})

_STANCE_GLOSSARY = {
    "unknown": "No adequate evidence in this case establishes either the proposition or its negation.",
    "suspended": "A position is temporarily withheld because a specified unresolved reliability or process concern prevents a verdict.",
    "provisionally_supported": "Adequate evidence supports the proposition, with a material stated limitation.",
    "supported": "The supplied adequate evidence supports the proposition.",
    "contested": "Material credible evidence supports both the proposition and its negation, with no justified resolution in this case.",
    "provisionally_contradicted": "Adequate evidence supports the proposition's negation, with a material stated limitation.",
    "contradicted": "The supplied adequate evidence supports the proposition's negation.",
    "superseded": "A newer justified position has replaced the earlier position for this same proposition.",
}


def build_response_instructions(
    *, reason_code_vocabulary: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build the neutral response contract shared by prompt and scorer.

    When no reason-code vocabulary is preregistered, reason codes are explicitly
    descriptive and must not be included in accuracy scoring. When a vocabulary
    is supplied, the exact choices are exposed to the subject before inference.
    """
    vocabulary: tuple[str, ...] | None
    if reason_code_vocabulary is None:
        vocabulary = None
    else:
        vocabulary = tuple(reason_code_vocabulary)
        if (len(vocabulary) < 2
                or any(not isinstance(value, str) or not value.strip() for value in vocabulary)
                or len(vocabulary) != len(set(vocabulary))):
            raise ValueError("epistemic_reason_code_vocabulary_invalid")

    return {
        "required_fields": ["stance", "reason_code", "evidence_ids"],
        "stance_values": sorted(STANCE_VALUES),
        "stance_definitions": dict(_STANCE_GLOSSARY),
        "stance_scope": (
            "Stance describes the proposition, not a status word used to describe a source or object. "
            "For example, evidence that a permit was suspended does not by itself require the stance "
            "suspended; choose the stance that follows for the proposition."
        ),
        "reason_code_vocabulary": list(vocabulary) if vocabulary is not None else None,
        "reason_code_scoring": (
            "exact_match_to_exposed_preregistered_vocabulary"
            if vocabulary is not None
            else "free_form_descriptive_not_scored"
        ),
    }


def score_response(
    response_text: str,
    *,
    expected_stance: str,
    expected_evidence_ids: Iterable[str],
    expected_reason_code: str | None = None,
    reason_code_vocabulary: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Score declared fields without retroactively imposing a reason taxonomy."""
    expected_ids = tuple(expected_evidence_ids)
    vocabulary = (None if reason_code_vocabulary is None
                  else tuple(reason_code_vocabulary))
    if expected_stance not in STANCE_VALUES:
        raise ValueError("epistemic_expected_stance_invalid")
    if (any(not isinstance(x, str) or not x for x in expected_ids)
            or len(expected_ids) != len(set(expected_ids))):
        raise ValueError("epistemic_expected_evidence_ids_invalid")
    if vocabulary is not None:
        if (len(vocabulary) < 2
                or any(not isinstance(value, str) or not value.strip() for value in vocabulary)
                or len(vocabulary) != len(set(vocabulary))):
            raise ValueError("epistemic_reason_code_vocabulary_invalid")
        if expected_reason_code not in vocabulary:
            raise ValueError("epistemic_expected_reason_code_not_in_exposed_vocabulary")

    try:
        answer = json.loads(response_text)
    except (TypeError, json.JSONDecodeError):
        answer = None
    shape_valid = (
        isinstance(answer, Mapping)
        and set(answer) == {"stance", "reason_code", "evidence_ids"}
        and isinstance(answer.get("stance"), str)
        and isinstance(answer.get("reason_code"), str)
        and isinstance(answer.get("evidence_ids"), list)
        and all(isinstance(item, str) for item in answer["evidence_ids"])
    )
    stance_match = bool(shape_valid and answer["stance"] == expected_stance)
    evidence_match = bool(shape_valid and tuple(answer["evidence_ids"]) == expected_ids)
    reason_match: bool | None
    if vocabulary is None:
        reason_match = None
        reason_status = "not_scored_no_subject_exposed_vocabulary"
    else:
        reason_match = bool(shape_valid and answer["reason_code"] == expected_reason_code)
        reason_status = "exact_match_scored_against_exposed_vocabulary"

    scored_fields_match = shape_valid and stance_match and evidence_match and reason_match is not False
    if not shape_valid:
        outcome = "invalid_response_shape"
    elif reason_match is None and stance_match and evidence_match:
        outcome = "partial_key_match_reason_code_unscored"
    elif scored_fields_match:
        outcome = "all_preregistered_scored_fields_match"
    else:
        outcome = "scored_field_mismatch"
    return {
        "response_shape_valid": bool(shape_valid),
        "stance_correct": stance_match if shape_valid else False,
        "evidence_ids_exact_match": evidence_match if shape_valid else False,
        "reason_code_correct": (None if vocabulary is None
                                 else reason_match if shape_valid else False),
        "reason_code_scoring_status": reason_status,
        "scored_fields": (["stance", "evidence_ids"] if vocabulary is None
                          else ["stance", "evidence_ids", "reason_code"]),
        "all_preregistered_scored_fields_match": bool(scored_fields_match),
        "outcome": outcome,
    }


__all__ = ["STANCE_VALUES", "build_response_instructions", "score_response"]
