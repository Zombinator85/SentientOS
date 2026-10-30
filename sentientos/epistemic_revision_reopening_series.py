"""Compose correction scoring with a later evidence-justified reopening."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .epistemic_revision_qualification import (
    ObservationReader,
    RevisionCase,
    evaluate_pair,
)
from .governed_local_model_invocation import LocalModelInvocationReceipt
from .local_model_authority import digest_payload
from .persistent_epistemic_state import (
    EpistemicCognitiveProjection,
    semantic_packets_for_projection,
)

SCHEMA = "sentientos.epistemic_revision_reopening_series:v1"
CORRECTION_KINDS = frozenset({
    "contrary_evidence", "inference_correction", "outdated_evidence",
})
REOPENING_KINDS = frozenset({"contrary_evidence", "outdated_evidence"})


@dataclass(frozen=True)
class EpistemicCorrectionReopeningSeries:
    """Bind an initial correction to a later evidence-backed revision."""

    correction_case: RevisionCase
    reopening_case: RevisionCase

    def commitment(self) -> str:
        correction = self.correction_case
        reopening = self.reopening_case
        if (
            correction.kind not in CORRECTION_KINDS
            or reopening.kind not in REOPENING_KINDS
            or correction.proposition_id != reopening.proposition_id
            or correction.after_key != reopening.before_key
            or correction.after_prompt_digest != reopening.before_prompt_digest
            or reopening.before_key == reopening.after_key
            or not (set(reopening.after_key.evidence_ids)
                    - set(reopening.before_key.evidence_ids))
        ):
            raise ValueError("epistemic_correction_reopening_series_invalid")
        payload = {
            "schema_version": SCHEMA,
            "correction_case_commitment": correction.commitment(),
            "reopening_case_commitment": reopening.commitment(),
        }
        return "sha256:" + digest_payload(payload)


def evaluate_correction_reopening_series(
    *,
    series: EpistemicCorrectionReopeningSeries,
    initial_reader: ObservationReader,
    corrected_reader: ObservationReader,
    reopened_reader: ObservationReader,
    initial_observation_id: str,
    corrected_observation_id: str,
    reopened_observation_id: str,
    initial_projection: EpistemicCognitiveProjection,
    corrected_projection: EpistemicCognitiveProjection,
    reopened_projection: EpistemicCognitiveProjection,
    initial_prompt: str,
    corrected_prompt: str,
    reopened_prompt: str,
    initial_receipt: LocalModelInvocationReceipt,
    corrected_receipt: LocalModelInvocationReceipt,
    reopened_receipt: LocalModelInvocationReceipt,
) -> dict[str, Any]:
    """Score the correction and a later reopening without changing either.

    The reopening must add an active evidence binding that was absent from the
    corrected projection and that the answer key requires. The existing v3
    scorer validates each owner observation, complete packet delivery, receipt,
    canonical transition, and delivered answer.
    """
    commitment = series.commitment()
    observation_ids = (
        initial_observation_id,
        corrected_observation_id,
        reopened_observation_id,
    )
    if len(set(observation_ids)) != 3:
        raise ValueError("epistemic_reopening_observation_reuse")

    [corrected_packet] = semantic_packets_for_projection(corrected_projection)
    [reopened_packet] = semantic_packets_for_projection(reopened_projection)
    corrected_active_ids = {
        row["binding_id"] for row in corrected_packet["active_evidence_bindings"]
    }
    reopened_active_ids = {
        row["binding_id"] for row in reopened_packet["active_evidence_bindings"]
    }
    added_binding_ids = reopened_active_ids - corrected_active_ids
    keyed_new_ids = set(series.reopening_case.after_key.evidence_ids) - set(
        series.reopening_case.before_key.evidence_ids
    )
    added_evidence_reaches_key = bool(added_binding_ids) and keyed_new_ids <= added_binding_ids

    correction = evaluate_pair(
        case=series.correction_case,
        before_reader=initial_reader,
        after_reader=corrected_reader,
        before_observation_id=initial_observation_id,
        after_observation_id=corrected_observation_id,
        before_projection=initial_projection,
        after_projection=corrected_projection,
        before_prompt=initial_prompt,
        after_prompt=corrected_prompt,
        before_receipt=initial_receipt,
        after_receipt=corrected_receipt,
    )
    reopening = evaluate_pair(
        case=series.reopening_case,
        before_reader=corrected_reader,
        after_reader=reopened_reader,
        before_observation_id=corrected_observation_id,
        after_observation_id=reopened_observation_id,
        before_projection=corrected_projection,
        after_projection=reopened_projection,
        before_prompt=corrected_prompt,
        after_prompt=reopened_prompt,
        before_receipt=corrected_receipt,
        after_receipt=reopened_receipt,
    )

    statuses = (correction["status"], reopening["status"])
    if not added_evidence_reaches_key or "insufficient" in statuses:
        status = "insufficient"
    elif statuses == ("case_passed", "case_passed"):
        status = "series_passed"
    else:
        status = "series_failed"
    report: dict[str, Any] = {
        "schema_version": SCHEMA,
        "series_id": series.correction_case.case_id + ":" +
            series.reopening_case.case_id,
        "series_commitment": commitment,
        "status": status,
        "initial_correction": correction,
        "justified_reopening": reopening,
        "initial_correction_passed": correction["status"] == "case_passed",
        "reopening_passed": reopening["status"] == "case_passed"
            and added_evidence_reaches_key,
        "new_active_evidence_count": len(added_binding_ids),
        "new_evidence_reaches_answer_key": added_evidence_reaches_key,
        "real_model_qualification_established": False,
        "causal_claim_made": False,
        "oracle_independence_verified": False,
        "reopening_justification_independently_verified": False,
        "preregistration_timing_verified": False,
        "authority": False,
        "source_mutation_performed": False,
    }
    return {**report, "report_digest": "sha256:" + digest_payload(report)}


__all__ = [
    "EpistemicCorrectionReopeningSeries",
    "evaluate_correction_reopening_series",
]
