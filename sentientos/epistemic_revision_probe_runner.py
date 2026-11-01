"""Run one governed correction and unsupported-pressure series.

Each probe capture is persisted by the resident cognition owner before the
existing paired evaluator scores the four observations. This runner does not
retry an inference and does not expose the answer keys to the subject.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .epistemic_revision_stability_series import (
    EpistemicCorrectionPressureSeries, evaluate_correction_pressure_series,
)
from .epistemic_revision_qualification import RevisionCase, evaluate_pair
from .persistent_epistemic_state import (
    EpistemicCognitiveProjection, semantic_packets_for_projection,
)
from .resident_developmental_cognition import (
    ResidentDevelopmentalCognitionError, ResidentDevelopmentalCognitionOwner,
    VerifiedEpistemicRevisionProbeCapture,
)
from .world_state_board import WorldStateSnapshot, validate_snapshot


def run_epistemic_revision_pair_once(*, cognition: ResidentDevelopmentalCognitionOwner,
        case: RevisionCase, before_snapshot: WorldStateSnapshot,
        after_snapshot: WorldStateSnapshot,
        before_projection: EpistemicCognitiveProjection,
        after_projection: EpistemicCognitiveProjection,
        tick_prefix: str) -> dict[str, Any]:
    """Run one evidence or inference transition through the cognition owner.

    Both prompts are checked before the first invocation. Answer keys remain in
    the controller-side case object and are only supplied to the evaluator
    after both verified captures have been persisted.
    """
    if (not isinstance(cognition, ResidentDevelopmentalCognitionOwner)
            or not isinstance(case, RevisionCase)
            or case.kind not in {"contrary_evidence", "inference_correction",
                "outdated_evidence"}
            or not isinstance(tick_prefix, str) or not tick_prefix.strip()
            or len(tick_prefix) > 180):
        raise ResidentDevelopmentalCognitionError(
            "epistemic_revision_pair_configuration_invalid")
    case.commitment()
    if (before_projection.proposition_ids != (case.proposition_id,)
            or after_projection.proposition_ids != (case.proposition_id,)):
        raise ResidentDevelopmentalCognitionError(
            "epistemic_revision_pair_projection_mismatch")
    semantic_packets_for_projection(before_projection)
    semantic_packets_for_projection(after_projection)
    for snapshot in (before_snapshot, after_snapshot):
        if not validate_snapshot(snapshot).valid:
            raise ResidentDevelopmentalCognitionError(
                "epistemic_revision_pair_snapshot_invalid")

    conditions = (
        ("before", before_snapshot, before_projection, case.before_prompt_digest),
        ("after", after_snapshot, after_projection, case.after_prompt_digest),
    )
    for condition, snapshot, projection, expected_prompt_digest in conditions:
        preview = cognition.preview_epistemic_revision_probe_prompt(
            snapshot=snapshot, tick_id=f"{tick_prefix}:{condition}",
            prior_epistemic_state=projection)
        if preview.get("prompt_digest") != expected_prompt_digest:
            raise ResidentDevelopmentalCognitionError(
                "epistemic_revision_probe_prompt_digest_mismatch")

    captures: list[VerifiedEpistemicRevisionProbeCapture] = []
    for condition, snapshot, projection, expected_prompt_digest in conditions:
        result = cognition.run_epistemic_revision_probe_once(
            snapshot=snapshot, tick_id=f"{tick_prefix}:{condition}",
            prior_epistemic_state=projection,
            expected_prompt_digest=expected_prompt_digest)
        if (result.status != "epistemic_revision_probe_completed"
                or len(result.cognition_observation_ids) != 1):
            raise ResidentDevelopmentalCognitionError(
                "epistemic_revision_probe_observation_unavailable")
        captures.append(cognition.verified_epistemic_revision_probe_capture(
            result.cognition_observation_ids[0]))

    before, after = captures
    return evaluate_pair(case=case, before_reader=cognition, after_reader=cognition,
        before_observation_id=before.observation_id,
        after_observation_id=after.observation_id,
        before_projection=before_projection, after_projection=after_projection,
        before_prompt=before.prompt, after_prompt=after.prompt,
        before_receipt=before.receipt, after_receipt=after.receipt)


def run_correction_pressure_series_once(*, cognition: ResidentDevelopmentalCognitionOwner,
        series: EpistemicCorrectionPressureSeries,
        original_snapshot: WorldStateSnapshot,
        corrected_snapshot: WorldStateSnapshot,
        pressure_snapshot: WorldStateSnapshot,
        original_projection: EpistemicCognitiveProjection,
        corrected_projection: EpistemicCognitiveProjection,
        tick_prefix: str,
        after_captures_durable: Callable[
            [Sequence[VerifiedEpistemicRevisionProbeCapture]], None] | None = None,
        ) -> dict[str, Any]:
    """Capture and score a correction followed by a pressure-only comparison.

    All four exact prompts are first composed through the owner's no-inference
    preview path and checked against the sealed digests before the first
    invocation. The owner repeats each digest check immediately before its
    invocation. If any call or capture fails, prior captures remain in owner
    custody and this function does not retry or continue the series.
    """
    if (not isinstance(cognition, ResidentDevelopmentalCognitionOwner)
            or not isinstance(series, EpistemicCorrectionPressureSeries)
            or not isinstance(tick_prefix, str) or not tick_prefix.strip()
            or len(tick_prefix) > 180):
        raise ResidentDevelopmentalCognitionError(
            "epistemic_revision_series_configuration_invalid")
    series.commitment()
    if (original_projection.proposition_ids !=
            (series.correction_case.proposition_id,)
            or corrected_projection.proposition_ids !=
                (series.correction_case.proposition_id,)):
        raise ResidentDevelopmentalCognitionError(
            "epistemic_revision_series_projection_mismatch")
    for snapshot in (original_snapshot, corrected_snapshot, pressure_snapshot):
        if not validate_snapshot(snapshot).valid:
            raise ResidentDevelopmentalCognitionError(
                "epistemic_revision_series_snapshot_invalid")

    correction = series.correction_case
    pressure = series.pressure_pair.case
    conditions = (
        ("correction-before", original_snapshot, original_projection,
            correction.before_prompt_digest),
        ("correction-after", corrected_snapshot, corrected_projection,
            correction.after_prompt_digest),
        ("pressure-before", corrected_snapshot, corrected_projection,
            pressure.before_prompt_digest),
        ("pressure-after", pressure_snapshot, corrected_projection,
            pressure.after_prompt_digest),
    )
    for condition, snapshot, projection, expected_prompt_digest in conditions:
        preview = cognition.preview_epistemic_revision_probe_prompt(
            snapshot=snapshot, tick_id=f"{tick_prefix}:{condition}",
            prior_epistemic_state=projection)
        if preview.get("prompt_digest") != expected_prompt_digest:
            raise ResidentDevelopmentalCognitionError(
                "epistemic_revision_probe_prompt_digest_mismatch")

    captures: list[VerifiedEpistemicRevisionProbeCapture] = []
    for condition, snapshot, projection, expected_prompt_digest in conditions:
        result = cognition.run_epistemic_revision_probe_once(
            snapshot=snapshot, tick_id=f"{tick_prefix}:{condition}",
            prior_epistemic_state=projection,
            expected_prompt_digest=expected_prompt_digest)
        if (result.status != "epistemic_revision_probe_completed"
                or len(result.cognition_observation_ids) != 1):
            raise ResidentDevelopmentalCognitionError(
                "epistemic_revision_probe_observation_unavailable")
        observation_id = result.cognition_observation_ids[0]
        captures.append(cognition.verified_epistemic_revision_probe_capture(
            observation_id))

    correction_before, correction_after, pressure_before, pressure_after = captures
    if after_captures_durable is not None:
        after_captures_durable(tuple(captures))
    return evaluate_correction_pressure_series(series=series,
        correction_before_reader=cognition, correction_after_reader=cognition,
        pressure_before_reader=cognition, pressure_after_reader=cognition,
        correction_before_observation_id=correction_before.observation_id,
        correction_after_observation_id=correction_after.observation_id,
        pressure_before_observation_id=pressure_before.observation_id,
        pressure_after_observation_id=pressure_after.observation_id,
        original_projection=original_projection,
        corrected_projection=corrected_projection,
        pressure_before_projection=corrected_projection,
        pressure_after_projection=corrected_projection,
        correction_before_prompt=correction_before.prompt,
        correction_after_prompt=correction_after.prompt,
        pressure_before_prompt=pressure_before.prompt,
        pressure_after_prompt=pressure_after.prompt,
        correction_before_receipt=correction_before.receipt,
        correction_after_receipt=correction_after.receipt,
        pressure_before_receipt=pressure_before.receipt,
        pressure_after_receipt=pressure_after.receipt)


__all__ = ["run_epistemic_revision_pair_once",
    "run_correction_pressure_series_once"]
