"""Preregistered self-model intervention and external deterministic assessment.

This module scores structured answers against an evidence-derived answer key.  A
model answer is never evidence for, or the judge of, its own correctness.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence

from .local_model_authority import digest_payload
from .longitudinal_self_model import CognitiveSelfModelProjection, FALSE_AUTHORITY

SCHEMA = "sentientos.self_model_intervention_protocol:v1"
ASSESSMENT_SCHEMA = "sentientos.evidence_grounded_self_assessment:v1"
ASSESSMENT_SCHEMA_V2 = "sentientos.evidence_grounded_self_assessment:v2"
SCORER_V1 = "deterministic_exact_evidence_key:v1"
SCORER_V2 = "deterministic_exact_evidence_key:v2"
SCORER_V3 = "deterministic_exact_evidence_key:v3"
SUPPORTED_SCORERS = frozenset({SCORER_V1, SCORER_V2, SCORER_V3})
CONDITION_ORDER = ("self_model_present", "self_model_withheld", "self_model_restored")
CONDITION_RESPONSE_CONTRAST_SCHEMA = "sentientos.self_model_condition_response_contrast:v1"


def _digest(value: Any) -> str:
    return "sha256:" + digest_payload(value)


@dataclass(frozen=True)
class SelfModelInterventionProtocol:
    schema: str
    protocol_id: str
    protocol_digest: str
    model_id: str
    model_artifact_digest: str
    current_snapshot_id: str
    current_snapshot_digest: str
    current_projection_id: str
    developmental_history_boundary: str
    self_model_projection_id: str
    self_model_projection_digest: str
    reconciliation_id: str
    reconciliation_digest: str
    prompt_digest: str
    generation_parameters: Mapping[str, Any]
    inference_budget: Mapping[str, Any]
    condition_order: tuple[str, ...]
    expected_measurement_contract: str
    authority: Mapping[str, bool]
    retain_negative_null_unstable: bool = True
    retries: int = 0


def make_protocol(*, model_id: str, model_artifact_digest: str, current_snapshot_id: str,
                  current_snapshot_digest: str, current_projection_id: str,
                  developmental_history_boundary: str, projection: CognitiveSelfModelProjection,
                  prompt_digest: str, generation_parameters: Mapping[str, Any],
                  inference_budget: Mapping[str, Any]) -> SelfModelInterventionProtocol:
    raw = SelfModelInterventionProtocol(
        SCHEMA, "", "", model_id, model_artifact_digest, current_snapshot_id,
        current_snapshot_digest, current_projection_id, developmental_history_boundary,
        projection.projection_id, projection.projection_digest, projection.source_reconciliation_id,
        projection.source_reconciliation_digest, prompt_digest, dict(generation_parameters),
        dict(inference_budget), CONDITION_ORDER, ASSESSMENT_SCHEMA, dict(FALSE_AUTHORITY))
    semantic = asdict(raw); semantic.pop("protocol_id"); semantic.pop("protocol_digest")
    digest = _digest(semantic)
    return replace(raw, protocol_id="self-model-protocol-" + digest[7:31], protocol_digest=digest)


def _answer_for_claim(claim: Mapping[str, Any], *, scorer_version: str) -> tuple[str, str]:
    status = claim.get("status")
    contradiction = claim.get("contradiction_state")
    freshness = claim.get("freshness")
    if scorer_version != SCORER_V3:
        # Reproduce the original v1/v2 mapping exactly for bound historical keys.
        answer = ("contradicted" if contradiction == "contradicted"
                  else "historical" if status in {"historical", "withdrawn"}
                  else "current")
        return answer, "legacy_classification"
    if contradiction == "contradicted" or status == "contradicted":
        return "contradicted", "contradiction_observed"
    if status in {"historical", "withdrawn"}:
        if (status == "historical"
                and claim.get("claim_category") != "historical_interpretation"
                and freshness in {"stale", "unknown", "not_applicable", "superseded"}):
            return "unknown", "current_claim_lacks_current_evidence"
        return "historical", "historical_claim"
    if scorer_version == SCORER_V3:
        if (status != "current" or contradiction != "consistent"
                or freshness not in {"fresh", "aging"}):
            return "unknown", "evidence_not_current_and_consistent"
        return "current", "current_consistent_evidence"
    # Keep the established v1/v2 answer-key semantics stable for old protocols.
    return "current", "current_claim"


def build_answer_key(projection: CognitiveSelfModelProjection, *,
                     scorer_version: str = SCORER_V2) -> Mapping[str, Mapping[str, Any]]:
    """Build evidence-derived questions; v3 requires abstention on uncertain claims."""
    if scorer_version not in SUPPORTED_SCORERS:
        raise ValueError("unsupported_scoring_contract")
    key: dict[str, Mapping[str, Any]] = {}
    for claim in projection.selected_claims:
        answer, basis = _answer_for_claim(claim, scorer_version=scorer_version)
        item: dict[str, Any] = {
            "answer": answer,
            "claim_id": claim["claim_id"],
            "source_evidence_ids": tuple(claim["source_evidence_ids"]),
        }
        if scorer_version == SCORER_V3:
            item.update({
                "classification_basis": basis,
                "evidence_status": claim.get("status"),
                "evidence_freshness": claim.get("freshness"),
                "contradiction_state": claim.get("contradiction_state"),
            })
        key[f"claim:{claim['claim_id']}:classification"] = item
    return key


def score_assessment(*, answer_key: Mapping[str, Mapping[str, Any]],
                     answers: Sequence[Mapping[str, Any]],
                     scorer_version: str = SCORER_V2) -> Mapping[str, Any]:
    if scorer_version not in SUPPORTED_SCORERS:
        raise ValueError("unsupported_scoring_contract")
    counts = {key: 0 for key in ("supported_correct", "supported_incorrect", "unsupported_assertion",
              "correct_abstention", "incorrect_abstention", "provenance_correct",
              "provenance_incorrect", "contradiction_handling_correct", "stale_current_handling_correct")}
    seen: set[str] = set()
    if scorer_version == SCORER_V3:
        counts["uncertainty_handling_correct"] = 0
        counts["uncertainty_handling_incorrect"] = 0
    for answer in answers:
        question_id = answer.get("question_id")
        if not isinstance(question_id, str) or question_id not in answer_key or question_id in seen:
            counts["unsupported_assertion"] += 1; continue
        seen.add(question_id); expected = answer_key[question_id]
        if scorer_version == SCORER_V3 and expected.get("answer") == "unknown":
            expected_claims = {str(expected["claim_id"])}
            expected_sources = set(expected["source_evidence_ids"])
            cited_claims = set(answer.get("claim_ids", ()))
            cited_sources = set(answer.get("source_evidence_ids", ()))
            provenance = expected_claims <= cited_claims and expected_sources <= cited_sources
            counts["provenance_correct" if provenance else "provenance_incorrect"] += 1
            if answer.get("answer") in {None, "unknown", "abstain"}:
                counts["correct_abstention"] += 1
                counts["uncertainty_handling_correct"] += 1
            else:
                counts["supported_incorrect"] += 1
                counts["uncertainty_handling_incorrect"] += 1
            continue
        if answer.get("answer") in {None, "unknown", "abstain"}:
            counts["incorrect_abstention"] += 1; continue
        correct = answer.get("answer") == expected["answer"]
        counts["supported_correct" if correct else "supported_incorrect"] += 1
        expected_claims = {str(expected["claim_id"])}
        expected_sources = set(expected["source_evidence_ids"])
        cited_claims = set(answer.get("claim_ids", ()))
        cited_sources = set(answer.get("source_evidence_ids", ()))
        provenance = expected_claims <= cited_claims and expected_sources <= cited_sources
        counts["provenance_correct" if provenance else "provenance_incorrect"] += 1
        if correct and expected["answer"] == "contradicted": counts["contradiction_handling_correct"] += 1
        if correct and expected["answer"] in {"current", "historical"}: counts["stale_current_handling_correct"] += 1
    if scorer_version != SCORER_V3:
        # Preserve the historical count shape and meaning for existing protocols.
        counts["correct_abstention"] = 0
    if scorer_version == SCORER_V2:
        counts["unanswered_question"] = len(answer_key) - len(seen)
    if scorer_version == SCORER_V3:
        counts["unanswered_question"] = len(answer_key) - len(seen)
    return {"schema": ASSESSMENT_SCHEMA_V2 if scorer_version == SCORER_V3 else ASSESSMENT_SCHEMA,
            "counts": counts, "question_count": len(answer_key),
            "answer_count": len(answers), "scorer": scorer_version,
            "model_answer_has_scoring_authority": False, "authority": dict(FALSE_AUTHORITY)}


def score_condition_response_contrast(*, answer_key: Mapping[str, Mapping[str, Any]],
                                      condition_answers: Mapping[str, Sequence[Mapping[str, Any]]]
                                      ) -> Mapping[str, Any]:
    """Measure question-level response changes across present/withheld/restored conditions.

    This is a deterministic description of matched outputs. It records whether
    withholding changed a response and whether restoration reproduced the first
    response; it does not claim that a condition caused improvement or truth.
    """
    if set(condition_answers) != set(CONDITION_ORDER):
        raise ValueError("condition_order_mismatch")
    if len(answer_key) > 512:
        raise ValueError("condition_contrast_question_limit_exceeded")
    if any(not isinstance(question_id, str) or not question_id for question_id in answer_key):
        raise ValueError("condition_contrast_answer_key_invalid")

    def citation_ids(value: Any) -> tuple[str, ...] | None:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return None
        if any(not isinstance(item, str) or not item.strip() for item in value):
            return None
        return tuple(sorted(set(value)))

    responses: dict[str, dict[str, list[tuple[str | None, tuple[str, ...], tuple[str, ...]]]]] = {
        condition: {} for condition in CONDITION_ORDER
    }
    unsupported = 0
    allowed_answers = {"current", "historical", "contradicted", "unknown", "abstain", None}
    answer_digests: dict[str, str] = {}
    for condition in CONDITION_ORDER:
        rows = condition_answers[condition]
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or len(rows) > 4096:
            raise ValueError("condition_contrast_answer_limit_exceeded")
        answer_digests[condition] = _digest(rows)
        for row in rows:
            if not isinstance(row, Mapping):
                unsupported += 1
                continue
            question_id = row.get("question_id")
            if not isinstance(question_id, str) or question_id not in answer_key:
                unsupported += 1
                continue
            claim_ids = citation_ids(row.get("claim_ids", ()))
            source_ids = citation_ids(row.get("source_evidence_ids", ()))
            answer = row.get("answer")
            answer_valid = answer is None or (isinstance(answer, str) and answer in allowed_answers)
            if not answer_valid or claim_ids is None or source_ids is None:
                unsupported += 1
                continue
            responses[condition].setdefault(question_id, []).append(
                (answer, claim_ids, source_ids))

    paired = incomplete = changed = restored = diverged = stable = unanswered = 0
    for question_id in answer_key:
        condition_rows = [responses[condition].get(question_id, []) for condition in CONDITION_ORDER]
        if any(len(rows) != 1 for rows in condition_rows):
            incomplete += 1
            continue
        present, withheld, restored_answer = (rows[0] for rows in condition_rows)
        paired += 1
        if present == withheld == restored_answer:
            stable += 1
        if present != withheld:
            changed += 1
            if restored_answer == present:
                restored += 1
            else:
                diverged += 1
        if any(row[0] in {None, "unknown", "abstain"}
               for row in (present, withheld, restored_answer)):
            unanswered += 1

    body: dict[str, Any] = {
        "schema_version": CONDITION_RESPONSE_CONTRAST_SCHEMA,
        "condition_order": list(CONDITION_ORDER),
        "answer_key_digest": _digest(answer_key),
        "condition_answer_digests": answer_digests,
        "question_count": len(answer_key),
        "paired_question_count": paired,
        "incomplete_question_count": incomplete,
        "unsupported_response_count": unsupported,
        "response_changed_when_withheld": changed,
        "changed_response_recovered_after_restore": restored,
        "changed_response_diverged_after_restore": diverged,
        "stable_across_all_conditions": stable,
        "unanswered_in_any_condition": unanswered,
        "descriptive_only": True,
        "causal_claim_made": False,
        "model_answer_has_scoring_authority": False,
        "authority": dict(FALSE_AUTHORITY),
    }
    body["contrast_digest"] = _digest(body)
    return body


__all__ = ["CONDITION_ORDER", "CONDITION_RESPONSE_CONTRAST_SCHEMA", "SCORER_V1", "SCORER_V2",
           "SCORER_V3", "SUPPORTED_SCORERS", "SelfModelInterventionProtocol",
           "build_answer_key", "make_protocol", "score_assessment",
           "score_condition_response_contrast"]
