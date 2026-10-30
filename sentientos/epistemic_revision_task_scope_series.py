"""Bind evidence-revision observations to an exact task target and time window."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .epistemic_revision_qualification import ObservationReader
from .epistemic_revision_stability_series import (
    EpistemicCorrectionInterruptionSeries,
    evaluate_correction_interruption_series,
)
from .governed_local_model_invocation import LocalModelInvocationReceipt
from .local_model_authority import digest_payload
from .persistent_epistemic_state import (
    EpistemicCognitiveProjection,
    semantic_packets_for_projection,
)

SCHEMA = "sentientos.epistemic_task_scope:v1"
RESULT_SCHEMA = "sentientos.epistemic_revision_task_scope_series:v1"
MAX_BYTES = 1_048_576
_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SCOPE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def _canonical(value: Any) -> str:
    result = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(result.encode("utf-8")) > MAX_BYTES:
        raise ValueError("epistemic_task_scope_input_limit_exceeded")
    return str(result)


def _digest(value: Any) -> str:
    return "sha256:" + str(digest_payload(value))


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("epistemic_task_scope_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("epistemic_task_scope_timestamp_invalid") from exc
    if parsed.tzinfo != timezone.utc or parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("epistemic_task_scope_timestamp_noncanonical")
    return parsed


@dataclass(frozen=True)
class EpistemicTaskScope:
    """Operator-stipulated repository target, half-open time window, and sources.

    The composer binds these fields to the exact context delivered to cognition.
    It does not verify Git ancestry, repository truth, or whether listed sources
    actually belong in the stipulated interval.
    """

    scope_id: str
    repository: str
    target_ref: str
    base_commit_sha: str
    head_commit_sha: str
    window_start_utc: str
    window_end_utc: str
    in_scope_source_artifact_ids: tuple[str, ...]

    def commitment(self) -> str:
        if (not isinstance(self.scope_id, str) or not _SCOPE_ID.fullmatch(self.scope_id)
                or not isinstance(self.repository, str) or not _REPOSITORY.fullmatch(self.repository)
                or not isinstance(self.target_ref, str) or not self.target_ref.strip()
                or len(self.target_ref) > 128
                or not isinstance(self.base_commit_sha, str) or not _SHA.fullmatch(self.base_commit_sha)
                or not isinstance(self.head_commit_sha, str) or not _SHA.fullmatch(self.head_commit_sha)):
            raise ValueError("epistemic_task_scope_identity_invalid")
        start, end = _timestamp(self.window_start_utc), _timestamp(self.window_end_utc)
        if start >= end:
            raise ValueError("epistemic_task_scope_window_invalid")
        sources = self.in_scope_source_artifact_ids
        if (not isinstance(sources, tuple) or not 1 <= len(sources) <= 256
                or any(not isinstance(item, str) or not item.strip() or len(item) > 256
                       for item in sources)
                or len(set(sources)) != len(sources)):
            raise ValueError("epistemic_task_scope_sources_invalid")
        payload = {"schema_version": SCHEMA, "scope_id": self.scope_id,
            "repository": self.repository, "target_ref": self.target_ref,
            "base_commit_sha": self.base_commit_sha, "head_commit_sha": self.head_commit_sha,
            "window_semantics": "[start,end)", "window_start_utc": self.window_start_utc,
            "window_end_utc": self.window_end_utc,
            "in_scope_source_artifact_ids": list(sources)}
        _canonical(payload)
        return _digest(payload)

    def fact_payload(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA, "scope_id": self.scope_id,
            "scope_digest": self.commitment(), "repository": self.repository,
            "target_ref": self.target_ref, "base_commit_sha": self.base_commit_sha,
            "head_commit_sha": self.head_commit_sha, "window_semantics": "[start,end)",
            "window_start_utc": self.window_start_utc, "window_end_utc": self.window_end_utc,
            "in_scope_source_artifact_ids": list(self.in_scope_source_artifact_ids)}


@dataclass(frozen=True)
class EpistemicTaskScopeInterruptionSeries:
    """Bind a task scope to one existing correction/interruption series."""

    series: EpistemicCorrectionInterruptionSeries
    task_scope: EpistemicTaskScope

    def commitment(self) -> str:
        return _digest({"schema_version": RESULT_SCHEMA,
            "interruption_series_commitment": self.series.commitment(),
            "task_scope_commitment": self.task_scope.commitment()})


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("epistemic_task_scope_duplicate_json_key")
        result[key] = value
    return result


def _context(prompt: str) -> dict[str, Any]:
    if not isinstance(prompt, str) or len(prompt.encode("utf-8")) > MAX_BYTES:
        raise ValueError("epistemic_task_scope_prompt_invalid")
    value = json.loads(prompt, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("epistemic_task_scope_prompt_invalid")
    _canonical(value)
    return value


def _scope_observation(*, reader: ObservationReader, observation_id: str,
        prompt: str, scope: EpistemicTaskScope) -> tuple[str, list[str]]:
    context = _context(prompt)
    current = context.get("current_evidence")
    if not isinstance(current, Mapping):
        return "missing", ["current_evidence_missing"]
    facts, sources, fact_ids = current.get("facts"), current.get("sources"), current.get("fact_ids")
    if not isinstance(facts, list) or not isinstance(sources, list) or not isinstance(fact_ids, list):
        return "missing", ["current_evidence_shape_invalid"]
    matches: list[Mapping[str, Any]] = []
    for fact in facts:
        if not isinstance(fact, Mapping):
            return "missing", ["current_fact_invalid"]
        payload = fact.get("payload")
        if isinstance(payload, Mapping) and "epistemic_task_scope" in payload:
            matches.append(fact)
    if len(matches) == 0:
        return "missing", ["task_scope_fact_missing"]
    if len(matches) != 1:
        return "missing", ["task_scope_fact_count_invalid"]
    fact = matches[0]
    fact_id = fact.get("fact_id")
    expected_source_id = "task-scope:" + scope.scope_id
    source = fact.get("source")
    source_rows = [row for row in sources if isinstance(row, Mapping)
        and row.get("source_id") == expected_source_id]
    violations: list[str] = []
    if (dict(fact.get("payload", {})) != {"epistemic_task_scope": scope.fact_payload()}
            or fact.get("stage") != "observation"
            or fact.get("disposition") != "recorded"
            or fact.get("effect_claimed") is not False
            or fact.get("effect_proven") is not False):
        violations.append("task_scope_fact_mismatch")
    if (not isinstance(fact_id, str) or fact_id not in fact_ids
            or not isinstance(source, Mapping)
            or source.get("source_id") != expected_source_id
            or source.get("kind") != "owner_introspection"
            or len(source_rows) != 1
            or source_rows[0].get("kind") != "owner_introspection"):
        violations.append("task_scope_source_binding_invalid")
    observation = reader.verified_cognition_observation(observation_id)
    delivered = observation.get("current_fact_ids")
    if not isinstance(delivered, (list, tuple)) or fact_id not in delivered:
        return "missing", [*violations, "task_scope_fact_not_delivered"]
    return ("mismatch" if violations else "verified"), violations


def _out_of_scope_active_sources(projection: EpistemicCognitiveProjection,
        scope: EpistemicTaskScope) -> list[str]:
    allowed = set(scope.in_scope_source_artifact_ids)
    start, end = _timestamp(scope.window_start_utc), _timestamp(scope.window_end_utc)
    [packet] = semantic_packets_for_projection(projection)
    violations: list[str] = []
    for binding in packet["active_evidence_bindings"]:
        source_id = binding.get("source_artifact_id")
        observed = binding.get("observation_time")
        if source_id not in allowed:
            violations.append("active_evidence_source_outside_scope")
            continue
        try:
            observed_at = _timestamp(observed)
        except ValueError:
            violations.append("active_evidence_time_invalid")
            continue
        if not start <= observed_at < end:
            violations.append("active_evidence_time_outside_scope")
    return violations


def evaluate_task_scoped_interruption_series(*,
        series: EpistemicTaskScopeInterruptionSeries,
        correction_before_reader: ObservationReader,
        correction_after_reader: ObservationReader,
        interruption_after_reader: ObservationReader,
        correction_before_observation_id: str,
        corrected_observation_id: str,
        interruption_observation_id: str,
        original_projection: EpistemicCognitiveProjection,
        corrected_projection: EpistemicCognitiveProjection,
        interruption_projection: EpistemicCognitiveProjection,
        correction_before_prompt: str,
        corrected_prompt: str,
        interruption_prompt: str,
        correction_before_receipt: LocalModelInvocationReceipt,
        corrected_receipt: LocalModelInvocationReceipt,
        interruption_receipt: LocalModelInvocationReceipt) -> dict[str, Any]:
    """Score correction and session resumption with one unchanged task scope."""
    commitment = series.commitment()
    scope = series.task_scope
    phases = (
        ("before", correction_before_reader, correction_before_observation_id,
            correction_before_prompt, original_projection),
        ("corrected", correction_after_reader, corrected_observation_id,
            corrected_prompt, corrected_projection),
        ("resumed", interruption_after_reader, interruption_observation_id,
            interruption_prompt, interruption_projection),
    )
    phase_reports: dict[str, Any] = {}
    scope_violations: list[str] = []
    missing_scope = False
    for name, reader, observation_id, prompt, projection in phases:
        delivery_status, delivery_violations = _scope_observation(
            reader=reader, observation_id=observation_id, prompt=prompt, scope=scope)
        source_violations = _out_of_scope_active_sources(projection, scope)
        if delivery_status == "missing":
            missing_scope = True
        scope_violations.extend(f"{name}:{code}" for code in delivery_violations)
        scope_violations.extend(f"{name}:{code}" for code in source_violations)
        phase_reports[name] = {"scope_delivery_status": delivery_status,
            "scope_fact_delivered": delivery_status != "missing",
            "active_evidence_scope_violations": source_violations}

    measured = evaluate_correction_interruption_series(
        series=series.series,
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
    # A delivered but wrong scope is itself a measured task failure. The core
    # scorer may mark its comparison insufficient because the altered scope
    # changes prompt content; preserve that detail in its nested report while
    # surfacing the independently detected scope violation as failure.
    status = ("insufficient" if missing_scope
        else "series_failed" if scope_violations or measured["status"] == "series_failed"
        else "insufficient" if measured["status"] == "insufficient"
        else "series_passed")
    report = {"schema_version": RESULT_SCHEMA,
        "series_id": measured["series_id"], "series_commitment": commitment,
        "task_scope_commitment": scope.commitment(), "status": status,
        "task_scope_preserved": not missing_scope and not scope_violations,
        "task_scope_phase_results": phase_reports,
        "scope_violation_codes": sorted(set(scope_violations)),
        "revision_series": measured,
        "repository_history_truth_verified": False,
        "repository_range_ancestry_verified": False,
        "time_window_independently_verified": False,
        "real_model_qualification_established": False,
        "causal_claim_made": False,
        "oracle_independence_verified": False,
        "preregistration_timing_verified": False,
        "authority": False, "source_mutation_performed": False}
    return {**report, "report_digest": _digest(report)}


__all__ = ["EpistemicTaskScope", "EpistemicTaskScopeInterruptionSeries",
    "evaluate_task_scoped_interruption_series"]
