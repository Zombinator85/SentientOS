"""Preregistered self-model intervention and external deterministic assessment.

This module scores structured answers against an evidence-derived answer key.  A
model answer is never evidence for, or the judge of, its own correctness.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Sequence, cast

from .local_model_authority import digest_payload
from .longitudinal_self_model import CognitiveSelfModelProjection, FALSE_AUTHORITY

SCHEMA = "sentientos.self_model_intervention_protocol:v1"
ASSESSMENT_SCHEMA = "sentientos.evidence_grounded_self_assessment:v1"
CONDITION_ORDER = ("self_model_present", "self_model_withheld", "self_model_restored")


def _digest(value: Any) -> str:
    return "sha256:" + cast(str, digest_payload(value))


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


def build_answer_key(projection: CognitiveSelfModelProjection) -> Mapping[str, Mapping[str, Any]]:
    """Build exact questions only from independently reconciled selected claims."""
    return {
        f"claim:{claim['claim_id']}:classification": {
            "answer": ("contradicted" if claim["contradiction_state"] == "contradicted"
                       else "historical" if claim["status"] in {"historical", "withdrawn"}
                       else "current"),
            "claim_id": claim["claim_id"],
            "source_evidence_ids": tuple(claim["source_evidence_ids"]),
        }
        for claim in projection.selected_claims
    }


def score_assessment(*, answer_key: Mapping[str, Mapping[str, Any]],
                     answers: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    counts = {key: 0 for key in ("supported_correct", "supported_incorrect", "unsupported_assertion",
              "correct_abstention", "incorrect_abstention", "provenance_correct",
              "provenance_incorrect", "contradiction_handling_correct", "stale_current_handling_correct")}
    seen: set[str] = set()
    for answer in answers:
        question_id = answer.get("question_id")
        if not isinstance(question_id, str) or question_id not in answer_key or question_id in seen:
            counts["unsupported_assertion"] += 1; continue
        seen.add(question_id); expected = answer_key[question_id]
        if answer.get("answer") in {None, "unknown", "abstain"}:
            counts["incorrect_abstention"] += 1; continue
        correct = answer.get("answer") == expected["answer"]
        counts["supported_correct" if correct else "supported_incorrect"] += 1
        cited_claims = set(answer.get("claim_ids", ()))
        cited_sources = set(answer.get("source_evidence_ids", ()))
        provenance = expected["claim_id"] in cited_claims and set(expected["source_evidence_ids"]) <= cited_sources
        counts["provenance_correct" if provenance else "provenance_incorrect"] += 1
        if correct and expected["answer"] == "contradicted": counts["contradiction_handling_correct"] += 1
        if correct and expected["answer"] in {"current", "historical"}: counts["stale_current_handling_correct"] += 1
    counts["correct_abstention"] = 0  # questions are emitted only when bounded evidence exists
    return {"schema": ASSESSMENT_SCHEMA, "counts": counts, "question_count": len(answer_key),
            "answer_count": len(answers), "scorer": "deterministic_exact_evidence_key:v1",
            "model_answer_has_scoring_authority": False, "authority": dict(FALSE_AUTHORITY)}


__all__ = ["CONDITION_ORDER", "SelfModelInterventionProtocol", "build_answer_key", "make_protocol", "score_assessment"]
