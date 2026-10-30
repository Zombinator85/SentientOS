"""Compose an evidence correction check followed by a pressure-resistance check.

The series reuses the existing paired scorers and consumes four owner-verified
observations. It does not invoke inference or change persistent state.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .epistemic_revision_pressure_control import (
    UnsupportedPressurePair, evaluate_unsupported_pressure_pair,
)
from .epistemic_revision_qualification import (
    ObservationReader, RevisionCase, evaluate_pair,
)
from .governed_local_model_invocation import LocalModelInvocationReceipt
from .local_model_authority import digest_payload
from .persistent_epistemic_state import (
    EpistemicCognitiveProjection, MeaningBearingEpistemicCognitiveProjection,
)

SCHEMA = "sentientos.epistemic_correction_pressure_series:v1"
MODEL_REPLACEMENT_SCHEMA = "sentientos.epistemic_correction_model_replacement_series:v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return "sha256:" + digest_payload(value)


@dataclass(frozen=True)
class EpistemicCorrectionPressureSeries:
    correction_case: RevisionCase
    pressure_pair: UnsupportedPressurePair

    def commitment(self) -> str:
        if (self.correction_case.kind != "contrary_evidence"
                or self.pressure_pair.case.proposition_id != self.correction_case.proposition_id
                or self.correction_case.after_key != self.pressure_pair.case.before_key
                or self.pressure_pair.case.before_key != self.pressure_pair.case.after_key):
            raise ValueError("epistemic_correction_pressure_series_invalid")
        payload = {"correction_case_commitment": self.correction_case.commitment(),
            "pressure_pair_commitment": self.pressure_pair.commitment()}
        return _digest(payload)


@dataclass(frozen=True)
class EpistemicCorrectionModelReplacementSeries:
    """Bind one justified correction to a later successor-model response."""

    correction_case: RevisionCase
    replacement_case: RevisionCase

    def commitment(self) -> str:
        correction = self.correction_case
        replacement = self.replacement_case
        if (correction.kind not in {"contrary_evidence", "inference_correction"}
                or replacement.kind != "model_replacement"
                or correction.proposition_id != replacement.proposition_id
                or correction.after_key != replacement.before_key
                or replacement.before_key != replacement.after_key):
            raise ValueError("epistemic_correction_model_replacement_invalid")
        payload = {"correction_case_commitment": correction.commitment(),
            "replacement_case_commitment": replacement.commitment()}
        return _digest(payload)


def evaluate_correction_pressure_series(*, series: EpistemicCorrectionPressureSeries,
        correction_before_reader: ObservationReader,
        correction_after_reader: ObservationReader,
        pressure_before_reader: ObservationReader,
        pressure_after_reader: ObservationReader,
        correction_before_observation_id: str,
        correction_after_observation_id: str,
        pressure_before_observation_id: str,
        pressure_after_observation_id: str,
        original_projection: EpistemicCognitiveProjection,
        corrected_projection: EpistemicCognitiveProjection,
        pressure_before_projection: EpistemicCognitiveProjection,
        pressure_after_projection: EpistemicCognitiveProjection,
        correction_before_prompt: str, correction_after_prompt: str,
        pressure_before_prompt: str, pressure_after_prompt: str,
        correction_before_receipt: LocalModelInvocationReceipt,
        correction_after_receipt: LocalModelInvocationReceipt,
        pressure_before_receipt: LocalModelInvocationReceipt,
        pressure_after_receipt: LocalModelInvocationReceipt) -> dict[str, Any]:
    """Score correction first, then resistance under unchanged corrected state."""
    commitment = series.commitment()
    observation_ids = (correction_before_observation_id,
        correction_after_observation_id, pressure_before_observation_id,
        pressure_after_observation_id)
    if len(set(observation_ids)) != 4:
        raise ValueError("epistemic_series_observation_reuse")
    corrected_digest = corrected_projection.projection_digest
    if any(projection.projection_digest != corrected_digest for projection in (
            pressure_before_projection, pressure_after_projection)):
        raise ValueError("epistemic_pressure_must_use_exact_corrected_projection")
    correction = evaluate_pair(case=series.correction_case,
        before_reader=correction_before_reader, after_reader=correction_after_reader,
        before_observation_id=correction_before_observation_id,
        after_observation_id=correction_after_observation_id,
        before_projection=original_projection, after_projection=corrected_projection,
        before_prompt=correction_before_prompt, after_prompt=correction_after_prompt,
        before_receipt=correction_before_receipt, after_receipt=correction_after_receipt)
    pressure = evaluate_unsupported_pressure_pair(pair=series.pressure_pair,
        before_reader=pressure_before_reader, after_reader=pressure_after_reader,
        before_observation_id=pressure_before_observation_id,
        after_observation_id=pressure_after_observation_id,
        before_projection=pressure_before_projection,
        after_projection=pressure_after_projection,
        before_prompt=pressure_before_prompt, after_prompt=pressure_after_prompt,
        before_receipt=pressure_before_receipt, after_receipt=pressure_after_receipt)
    statuses = (correction["status"], pressure["status"])
    status = ("insufficient" if "insufficient" in statuses else
        "series_passed" if statuses == ("case_passed", "case_passed") else "series_failed")
    report = {"schema_version": SCHEMA,
        "series_id": series.correction_case.case_id + ":" + series.pressure_pair.case.case_id,
        "series_commitment": commitment, "status": status,
        "correction": correction, "pressure_resistance": pressure,
        "correction_measurement_passed": correction["status"] == "case_passed",
        "pressure_resistance_passed": pressure["status"] == "case_passed",
        "real_model_qualification_established": False,
        "causal_claim_made": False, "oracle_independence_verified": False,
        "preregistration_timing_verified": False, "authority": False,
        "source_mutation_performed": False}
    return {**report, "report_digest": _digest(report)}


def evaluate_correction_model_replacement_series(*,
        series: EpistemicCorrectionModelReplacementSeries,
        correction_before_reader: ObservationReader,
        correction_after_reader: ObservationReader,
        replacement_after_reader: ObservationReader,
        correction_before_observation_id: str,
        corrected_observation_id: str,
        replacement_observation_id: str,
        original_projection: EpistemicCognitiveProjection,
        corrected_projection: EpistemicCognitiveProjection,
        replacement_projection: EpistemicCognitiveProjection,
        correction_before_prompt: str,
        corrected_prompt: str,
        replacement_prompt: str,
        correction_before_receipt: LocalModelInvocationReceipt,
        corrected_receipt: LocalModelInvocationReceipt,
        replacement_receipt: LocalModelInvocationReceipt) -> dict[str, Any]:
    """Score correction, then score its retention under a successor identity."""
    commitment = series.commitment()
    if len({correction_before_observation_id, corrected_observation_id,
            replacement_observation_id}) != 3:
        raise ValueError("epistemic_series_observation_reuse")
    if (corrected_projection.projection_digest
            != replacement_projection.projection_digest):
        raise ValueError("replacement_must_use_exact_corrected_projection")
    correction = evaluate_pair(case=series.correction_case,
        before_reader=correction_before_reader,
        after_reader=correction_after_reader,
        before_observation_id=correction_before_observation_id,
        after_observation_id=corrected_observation_id,
        before_projection=original_projection,
        after_projection=corrected_projection,
        before_prompt=correction_before_prompt,
        after_prompt=corrected_prompt,
        before_receipt=correction_before_receipt,
        after_receipt=corrected_receipt)
    replacement = evaluate_pair(case=series.replacement_case,
        before_reader=correction_after_reader,
        after_reader=replacement_after_reader,
        before_observation_id=corrected_observation_id,
        after_observation_id=replacement_observation_id,
        before_projection=corrected_projection,
        after_projection=replacement_projection,
        before_prompt=corrected_prompt,
        after_prompt=replacement_prompt,
        before_receipt=corrected_receipt,
        after_receipt=replacement_receipt)
    statuses = (correction["status"], replacement["status"])
    status = ("insufficient" if "insufficient" in statuses else
        "series_passed" if statuses == ("case_passed", "case_passed")
        else "series_failed")
    correction_events: tuple[Mapping[str, Any], ...] = ()
    if (isinstance(corrected_projection, MeaningBearingEpistemicCognitiveProjection)
            and len(corrected_projection.update_events) == 1):
        correction_events = corrected_projection.update_events[0]
    correction_event: Mapping[str, Any] = correction_events[-1] if correction_events else {}
    before_evidence_digest = (original_projection.evidence_set_digests[0]
        if len(original_projection.evidence_set_digests) == 1 else None)
    after_evidence_digest = (corrected_projection.evidence_set_digests[0]
        if len(corrected_projection.evidence_set_digests) == 1 else None)
    report = {"schema_version": MODEL_REPLACEMENT_SCHEMA,
        "series_id": series.correction_case.case_id + ":" +
            series.replacement_case.case_id,
        "series_commitment": commitment, "status": status,
        "correction": correction, "model_replacement_retention": replacement,
        "correction_measurement_passed": correction["status"] == "case_passed",
        "replacement_retention_passed": replacement["status"] == "case_passed",
        "correction_update_reason": correction_event.get("reason"),
        "correction_evidence_set_digest_before": before_evidence_digest,
        "correction_evidence_set_digest_after": after_evidence_digest,
        "correction_evidence_set_preserved": (before_evidence_digest is not None
            and before_evidence_digest == after_evidence_digest),
        "real_model_qualification_established": False,
        "causal_claim_made": False, "oracle_independence_verified": False,
        "preregistration_timing_verified": False, "authority": False,
        "source_mutation_performed": False}
    return {**report, "report_digest": _digest(report)}


__all__ = ["EpistemicCorrectionPressureSeries",
    "EpistemicCorrectionModelReplacementSeries",
    "evaluate_correction_pressure_series",
    "evaluate_correction_model_replacement_series"]
