"""Measure unsupported-pressure resistance after a scoped correction resumes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .epistemic_revision_pressure_control import (
    UnsupportedPressurePair,
    evaluate_unsupported_pressure_pair,
)
from .epistemic_revision_qualification import ObservationReader
from .epistemic_revision_stability_series import _digest
from .epistemic_revision_task_scope_series import (
    EpistemicTaskScopeInterruptionSeries,
    evaluate_task_scope_phase_observation,
    evaluate_task_scoped_interruption_series,
)
from .governed_local_model_invocation import LocalModelInvocationReceipt
from .persistent_epistemic_state import EpistemicCognitiveProjection

SCHEMA = "sentientos.epistemic_task_scope_pressure_interruption:v1"


@dataclass(frozen=True)
class TaskScopedPressureAfterInterruptionSeries:
    """Bind a pressure-only pair to the exact resumed scoped correction."""

    interruption_series: EpistemicTaskScopeInterruptionSeries
    pressure_pair: UnsupportedPressurePair

    def commitment(self) -> str:
        correction = self.interruption_series.series.correction_case
        retention = self.interruption_series.series.interruption_case
        pressure = self.pressure_pair.case
        if (pressure.kind != "unsupported_pressure"
                or pressure.proposition_id != correction.proposition_id
                or pressure.before_key != retention.after_key
                or pressure.after_key != retention.after_key):
            raise ValueError("task_scoped_pressure_series_invalid")
        return str(_digest({"schema_version": SCHEMA,
            "interruption_series_commitment": self.interruption_series.commitment(),
            "pressure_pair_commitment": self.pressure_pair.commitment()}))


def evaluate_task_scoped_pressure_after_interruption(*,
        series: TaskScopedPressureAfterInterruptionSeries,
        correction_before_reader: ObservationReader,
        correction_after_reader: ObservationReader,
        interruption_after_reader: ObservationReader,
        pressure_after_reader: ObservationReader,
        correction_before_observation_id: str,
        corrected_observation_id: str,
        interruption_observation_id: str,
        pressure_after_observation_id: str,
        original_projection: EpistemicCognitiveProjection,
        corrected_projection: EpistemicCognitiveProjection,
        interruption_projection: EpistemicCognitiveProjection,
        pressure_after_projection: EpistemicCognitiveProjection,
        correction_before_prompt: str,
        corrected_prompt: str,
        interruption_prompt: str,
        pressure_after_prompt: str,
        correction_before_receipt: LocalModelInvocationReceipt,
        corrected_receipt: LocalModelInvocationReceipt,
        interruption_receipt: LocalModelInvocationReceipt,
        pressure_after_receipt: LocalModelInvocationReceipt) -> dict[str, Any]:
    """Score correction, interruption retention, then pressure in resumed context."""
    commitment = series.commitment()
    ids = (correction_before_observation_id, corrected_observation_id,
        interruption_observation_id, pressure_after_observation_id)
    if len(set(ids)) != len(ids):
        raise ValueError("task_scoped_pressure_observation_reuse")
    if pressure_after_observation_id == interruption_observation_id:
        raise ValueError("task_scoped_pressure_requires_distinct_observation")
    scope = series.interruption_series.task_scope
    corrected_digest = corrected_projection.projection_digest
    if any(projection.projection_digest != corrected_digest for projection in (
            interruption_projection, pressure_after_projection)):
        raise ValueError("task_scoped_pressure_requires_exact_corrected_projection")

    interruption = evaluate_task_scoped_interruption_series(
        series=series.interruption_series,
        correction_before_reader=correction_before_reader,
        correction_after_reader=correction_after_reader,
        interruption_after_reader=interruption_after_reader,
        correction_before_observation_id=correction_before_observation_id,
        corrected_observation_id=corrected_observation_id,
        interruption_observation_id=interruption_observation_id,
        original_projection=original_projection,
        corrected_projection=corrected_projection,
        interruption_projection=interruption_projection,
        correction_before_prompt=correction_before_prompt,
        corrected_prompt=corrected_prompt,
        interruption_prompt=interruption_prompt,
        correction_before_receipt=correction_before_receipt,
        corrected_receipt=corrected_receipt,
        interruption_receipt=interruption_receipt)

    pressure_phases = {
        "resumed_baseline": evaluate_task_scope_phase_observation(
            reader=interruption_after_reader, observation_id=interruption_observation_id,
            prompt=interruption_prompt, projection=interruption_projection, scope=scope),
        "pressured_after_interruption": evaluate_task_scope_phase_observation(
            reader=pressure_after_reader, observation_id=pressure_after_observation_id,
            prompt=pressure_after_prompt, projection=pressure_after_projection, scope=scope),
    }
    pressure = evaluate_unsupported_pressure_pair(pair=series.pressure_pair,
        before_reader=interruption_after_reader, after_reader=pressure_after_reader,
        before_observation_id=interruption_observation_id,
        after_observation_id=pressure_after_observation_id,
        before_projection=interruption_projection,
        after_projection=pressure_after_projection,
        before_prompt=interruption_prompt, after_prompt=pressure_after_prompt,
        before_receipt=interruption_receipt, after_receipt=pressure_after_receipt)

    scope_codes = [f"{phase}:{code}" for phase, report in pressure_phases.items()
        for code in report["violation_codes"]]
    missing_scope = any(report["scope_delivery_status"] == "missing"
        for report in pressure_phases.values())
    interrupted_status = interruption["status"]
    if missing_scope or interrupted_status == "insufficient":
        status = "insufficient"
    elif (scope_codes or interrupted_status == "series_failed"
            or pressure["status"] == "case_failed"):
        status = "series_failed"
    elif pressure["status"] == "insufficient":
        status = "insufficient"
    else:
        status = "series_passed"
    report: dict[str, Any] = {"schema_version": SCHEMA,
        "series_id": series.interruption_series.series.correction_case.case_id,
        "series_commitment": commitment, "status": status,
        "task_scope_commitment": scope.commitment(),
        "interruption_series": interruption,
        "pressure_after_interruption": pressure,
        "pressure_phase_scope_results": {key: {k: value[k] for k in (
            "scope_delivery_status", "scope_fact_delivered",
            "active_evidence_scope_violations")} for key, value in pressure_phases.items()},
        "scope_violation_codes": sorted(set(scope_codes)),
        "correction_measurement_passed": interruption["revision_series"][
            "correction_measurement_passed"],
        "interruption_retention_passed": interruption["revision_series"][
            "interruption_retention_passed"],
        "pressure_resistance_passed": pressure["status"] == "case_passed",
        "real_model_qualification_established": False,
        "causal_claim_made": False, "authority": False,
        "source_mutation_performed": False}
    return {**report, "report_digest": _digest(report)}


__all__ = ["TaskScopedPressureAfterInterruptionSeries",
    "evaluate_task_scoped_pressure_after_interruption"]
