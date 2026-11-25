"""Validation and compact views for campaign schedule evidence."""
from __future__ import annotations

import re
from typing import Any, Mapping

from .developmental_model_replacement_conditions import (
    CONDITION_ORDER as MODEL_REPLACEMENT_CONDITION_ORDER,
    COUNTERBALANCED_CONDITION_ORDERS as MODEL_REPLACEMENT_EXECUTION_ORDERS)
from .developmental_model_replacement_experiment import _digest

def verified_campaign_condition_order_summary(
        fact: Mapping[str, Any]) -> dict[str, Any] | None:
    source, subject, payload = (fact.get("source"), fact.get("subject"),
        fact.get("payload"))
    source_schema = source.get("schema_version") if isinstance(source, Mapping) else None
    report_schema = payload.get("report_schema_version") if isinstance(payload, Mapping) else None
    schema_pair_valid = (
        source_schema == "sentientos.developmental_model_replacement_campaign_world_state_record:v2"
        and report_schema == "sentientos.developmental_model_replacement_campaign_report:v6"
        or source_schema == "sentientos.developmental_model_replacement_campaign_world_state_record:v3"
        and report_schema == "sentientos.developmental_model_replacement_campaign_report:v7")
    if (not isinstance(source, Mapping) or source.get("kind") != "embodiment"
            or not schema_pair_valid
            or not isinstance(subject, Mapping)
            or subject.get("subject_kind") != "developmental_model_replacement_campaign"
            or not isinstance(payload, Mapping)
            or payload.get("current_truth") is not False
            or payload.get("authority") is not False
            or payload.get("learning_established") is not False
            or not isinstance(payload.get("condition_order_summary"), Mapping)):
        return None
    for identity_key, digest_key, prefix in (
            ("campaign_id", "campaign_digest", "model-replacement-campaign-"),
            ("report_id", "report_digest", "model-replacement-campaign-report-")):
        identity, digest = payload.get(identity_key), payload.get(digest_key)
        if (not isinstance(digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
                or identity != prefix + digest[7:31]):
            return None
    summary = payload["condition_order_summary"]
    summary_keys = {"trial_schedules",
            "condition_position_counts_positions_1_to_5",
            "condition_outcomes_by_execution_position", "position_effect_estimated"}
    if report_schema == "sentientos.developmental_model_replacement_campaign_report:v7":
        summary_keys.add("order_evidence_limit")
        if summary.get("order_evidence_limit") != (
                "condition_start_digest_chain_is_structural_not_external_authentication"):
            return None
    if (set(summary) != summary_keys
            or summary.get("position_effect_estimated") is not False):
        return None
    schedules = summary.get("trial_schedules")
    trial_count = payload.get("trial_count")
    trial_refs = payload.get("trial_artifacts")
    if (type(trial_count) is not int or not 2 <= trial_count <= 32
            or not isinstance(schedules, list) or len(schedules) != trial_count
            or not isinstance(trial_refs, list) or len(trial_refs) != trial_count
            or schedule_has_posture and (payload.get("validity") !=
                "valid_completed_replication_campaign"
                or payload.get("planned_trial_count") != trial_count)):
        return None
    classifications = payload.get("classification_counts")
    if (not isinstance(classifications, Mapping) or not classifications
            or any(not isinstance(name, str) or type(value) is not int or value < 0
                for name, value in classifications.items())
            or sum(classifications.values()) != trial_count
            or payload.get("claims_posture") != "descriptive_exact_counts_only"
            or not isinstance(payload.get("non_claims"), list)
            or not all(isinstance(item, str) for item in payload["non_claims"])
            or "learning" not in payload["non_claims"]):
        return None
    referenced_trial_ids: list[str] = []
    for reference in trial_refs:
        if (not isinstance(reference, Mapping)
                or set(reference) != {"trial_id", "run_id", "run_digest"}
                or not isinstance(reference.get("trial_id"), str)
                or not isinstance(reference.get("run_id"), str)
                or not isinstance(reference.get("run_digest"), str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", reference["run_digest"]) is None
                or reference["run_id"] != "model-replacement-run-"
                    + reference["run_digest"][7:31]):
            return None
        referenced_trial_ids.append(reference["trial_id"])
    schedule_by_trial: dict[str, tuple[str, ...]] = {}
    schedule_counts = {order: 0 for order in MODEL_REPLACEMENT_EXECUTION_ORDERS}
    witness_protocol: tuple[str, str] | None = None
    schedule_has_posture = report_schema == (
        "sentientos.developmental_model_replacement_campaign_report:v7")
    expected_counts = {condition: [0] * len(MODEL_REPLACEMENT_CONDITION_ORDER)
        for condition in MODEL_REPLACEMENT_CONDITION_ORDER}
    for row in schedules:
        if (not isinstance(row, Mapping)
                or set(row) != ({"trial_id", "preregistered_order", "observed_order",
                    "condition_order_evidence_posture", "condition_start_witnesses"}
                    if schedule_has_posture else
                    {"trial_id", "preregistered_order", "observed_order"})):
            return None
        trial_id, planned, observed = (row.get("trial_id"),
            row.get("preregistered_order"), row.get("observed_order"))
        if (not isinstance(trial_id, str) or not trial_id or len(trial_id) > 128
                or trial_id in schedule_by_trial
                or not isinstance(planned, list) or not isinstance(observed, list)
                or any(type(condition) is not str for condition in planned + observed)
                or tuple(planned) not in MODEL_REPLACEMENT_EXECUTION_ORDERS
                or observed != planned):
            return None
        if schedule_has_posture and (not isinstance(
                row.get("condition_order_evidence_posture"), str)
                or row.get("condition_order_evidence_posture") not in {
                "condition_start_chain_digest_verified",
                "condition_start_position_digests_verified_without_chain",
                "legacy_condition_start_order_unattested",
                "legacy_run_without_condition_journal"}):
            return None
        if schedule_has_posture:
            posture = row["condition_order_evidence_posture"]
            witnesses = row.get("condition_start_witnesses")
            if (not isinstance(witnesses, list)
                    or len(witnesses) not in ({0, len(observed)}
                        if posture == "legacy_run_without_condition_journal"
                        else {len(observed)})):
                return None
            schemas: list[str] = []
            previous_digest: str | None = None
            for position, (condition, witness) in enumerate(zip(observed, witnesses), start=1):
                if not isinstance(witness, Mapping):
                    return None
                schema = witness.get("schema_version")
                if not isinstance(schema, str) or schema not in {
                        "sentientos.developmental_model_replacement_condition_start:v1",
                        "sentientos.developmental_model_replacement_condition_start:v2",
                        "sentientos.developmental_model_replacement_condition_start:v3"}:
                    return None
                schemas.append(schema)
                witness_keys = {"schema_version", "condition_id", "protocol_id",
                    "protocol_digest", "trial_id", "condition", "input_digest",
                    "correlation_id", "authority", "condition_start_digest"}
                if schema.endswith(":v2"):
                    witness_keys.update({"execution_order", "execution_position"})
                elif schema.endswith(":v3"):
                    witness_keys.update({"execution_order", "execution_position",
                        "previous_condition_start_digest"})
                semantic = {key: value for key, value in witness.items()
                    if key != "condition_start_digest"}
                digest = witness.get("condition_start_digest")
                protocol_id, protocol_digest = (witness.get("protocol_id"),
                    witness.get("protocol_digest"))
                identity = _digest({"protocol_id": protocol_id,
                    "trial_id": trial_id, "condition": condition})
                if (set(witness) != witness_keys
                        or digest != _digest(semantic)
                        or not isinstance(digest, str)
                        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
                        or not isinstance(protocol_id, str) or not protocol_id
                        or not isinstance(protocol_digest, str)
                        or re.fullmatch(r"sha256:[0-9a-f]{64}", protocol_digest) is None
                        or witness.get("condition_id") !=
                            "model-replacement-condition-" + identity[7:31]
                        or witness.get("trial_id") != trial_id
                        or witness.get("condition") != condition
                        or not isinstance(witness.get("input_digest"), str)
                        or re.fullmatch(r"sha256:[0-9a-f]{64}", witness["input_digest"]) is None
                        or witness.get("correlation_id") !=
                            f"{protocol_id}:{trial_id}:{condition}"
                        or witness.get("authority") is not False):
                    return None
                if schema.endswith((":v2", ":v3")) and (
                        witness.get("execution_order") != observed
                        or witness.get("execution_position") != position):
                    return None
                if schema.endswith(":v3") and (
                        witness.get("previous_condition_start_digest") != previous_digest):
                    return None
                if witness_protocol is None:
                    witness_protocol = (protocol_id, protocol_digest)
                elif witness_protocol != (protocol_id, protocol_digest):
                    return None
                previous_digest = str(digest)
            if witnesses:
                derived_posture = (
                    "legacy_condition_start_order_unattested"
                    if any(schema.endswith(":v1") for schema in schemas) else
                    "condition_start_chain_digest_verified"
                    if all(schema.endswith(":v3") for schema in schemas) else
                    "condition_start_position_digests_verified_without_chain")
                if derived_posture != posture:
                    return None
            elif posture != "legacy_run_without_condition_journal":
                return None
        schedule_by_trial[trial_id] = tuple(observed)
        schedule_counts[tuple(observed)] += 1
        for position, condition in enumerate(observed):
            expected_counts[condition][position] += 1
    if list(schedule_by_trial) != referenced_trial_ids:
        return None
    if max(schedule_counts.values()) - min(schedule_counts.values()) > 1:
        return None
    counts = summary.get("condition_position_counts_positions_1_to_5")
    if (not isinstance(counts, Mapping)
            or set(counts) != set(MODEL_REPLACEMENT_CONDITION_ORDER)
            or any(not isinstance(counts[condition], list)
                or len(counts[condition]) != len(MODEL_REPLACEMENT_CONDITION_ORDER)
                or any(type(value) is not int or value < 0
                    for value in counts[condition])
                or counts[condition] != expected_counts[condition]
                for condition in MODEL_REPLACEMENT_CONDITION_ORDER)):
        return None
    evidence = summary.get("condition_outcomes_by_execution_position")
    if not isinstance(evidence, list) or len(evidence) != trial_count * len(MODEL_REPLACEMENT_CONDITION_ORDER):
        return None
    seen: set[tuple[str, str]] = set()
    for row in evidence:
        if (not isinstance(row, Mapping)
                or set(row) != {"trial_id", "condition", "execution_position",
                    "output_digest", "objective_score_summary"}):
            return None
        trial_id, condition, position = (row.get("trial_id"), row.get("condition"),
            row.get("execution_position"))
        if (trial_id not in schedule_by_trial or condition not in MODEL_REPLACEMENT_CONDITION_ORDER
                or type(position) is not int or not 1 <= position <= 5
                or schedule_by_trial[trial_id][position - 1] != condition
                or (trial_id, condition) in seen
                or not isinstance(row.get("output_digest"), str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", row["output_digest"]) is None):
            return None
        seen.add((trial_id, condition))
        score = row.get("objective_score_summary")
        if score is not None:
            if (not isinstance(score, Mapping)
                    or set(score) != {"status", "correct", "correct_count",
                        "answered_count", "abstained_count", "probe_count"}
                    or not isinstance(score.get("status"), str)
                    or not score["status"] or len(score["status"]) > 64
                    or score.get("correct") is not None
                        and type(score.get("correct")) is not bool
                    or any(value is not None and (type(value) is not int or not 0 <= value <= 16)
                        for value in (score.get("correct_count"),
                            score.get("answered_count"), score.get("abstained_count"),
                            score.get("probe_count")))):
                return None
            probes, answered, abstained, correct = (score.get("probe_count"),
                score.get("answered_count"), score.get("abstained_count"),
                score.get("correct_count"))
            if (probes is not None and (answered is None or abstained is None
                    or answered + abstained != probes)
                    or correct is not None and answered is not None and correct > answered):
                return None
    if len(seen) != trial_count * len(MODEL_REPLACEMENT_CONDITION_ORDER):
        return None
    return {"trial_schedules": [dict(row) for row in schedules],
        "condition_position_counts_positions_1_to_5": {
            condition: list(expected_counts[condition])
            for condition in MODEL_REPLACEMENT_CONDITION_ORDER},
        "condition_outcomes_by_execution_position": [dict(row) for row in evidence],
        "order_evidence_limit": (summary.get("order_evidence_limit")
            if schedule_has_posture else
            "legacy_run_and_preregistered_order_claim_only"),
        "position_effect_estimated": False}


def compact_verified_campaign_condition_order_summary(
        fact: Mapping[str, Any]) -> dict[str, Any] | None:
    """Aggregate validated per-trial evidence for bounded writeback prompts."""
    verified = verified_campaign_condition_order_summary(fact)
    payload = fact.get("payload")
    if verified is None or not isinstance(payload, Mapping):
        return None
    schedule_counts = {order: 0 for order in MODEL_REPLACEMENT_EXECUTION_ORDERS}
    order_evidence_posture_counts: dict[str, int] = {}
    for row in verified["trial_schedules"]:
        schedule_counts[tuple(row["observed_order"])] += 1
        posture = str(row.get("condition_order_evidence_posture",
            "legacy_report_without_condition_order_posture"))
        order_evidence_posture_counts[posture] = (
            order_evidence_posture_counts.get(posture, 0) + 1)
    accumulators: dict[tuple[str, int], dict[str, Any]] = {
        (condition, position): {"trial_count": 0, "output_digests": set(),
            "objective_score_trial_count": 0, "objective_status_counts": {},
            "correct_count_sum": 0, "correct_count_observed_trials": 0,
            "answered_count_sum": 0, "answered_count_observed_trials": 0,
            "abstained_count_sum": 0, "abstained_count_observed_trials": 0,
            "probe_count_sum": 0, "probe_count_observed_trials": 0}
        for condition in MODEL_REPLACEMENT_CONDITION_ORDER
        for position in range(1, len(MODEL_REPLACEMENT_CONDITION_ORDER) + 1)}
    for row in verified["condition_outcomes_by_execution_position"]:
        key = (str(row["condition"]), int(row["execution_position"]))
        aggregate = accumulators[key]
        aggregate["trial_count"] += 1
        aggregate["output_digests"].add(row["output_digest"])
        score = row["objective_score_summary"]
        if not isinstance(score, Mapping):
            continue
        aggregate["objective_score_trial_count"] += 1
        status = str(score["status"])
        statuses = aggregate["objective_status_counts"]
        statuses[status] = statuses.get(status, 0) + 1
        for field in ("correct_count", "answered_count", "abstained_count", "probe_count"):
            value = score.get(field)
            if type(value) is int:
                sum_key = field + "_sum"
                count_key = field + "_observed_trials"
                aggregate[sum_key] += value
                aggregate[count_key] += 1
    grouped = []
    for condition in MODEL_REPLACEMENT_CONDITION_ORDER:
        for position in range(1, len(MODEL_REPLACEMENT_CONDITION_ORDER) + 1):
            raw = accumulators[(condition, position)]
            grouped.append({"condition": condition, "execution_position": position,
                "trial_count": raw["trial_count"],
                "unique_output_digest_count": len(raw["output_digests"]),
                "objective_score_trial_count": raw["objective_score_trial_count"],
                "objective_status_counts": dict(sorted(
                    raw["objective_status_counts"].items())),
                **{key: value for key, value in raw.items()
                    if key.endswith("_sum") or key.endswith("_observed_trials")}})
    return {"campaign_id": payload.get("campaign_id"),
        "campaign_digest": payload.get("campaign_digest"),
        "report_id": payload.get("report_id"),
        "report_digest": payload.get("report_digest"),
        "report_schema_version": payload.get("report_schema_version"),
        "trial_count": payload.get("trial_count"),
        "classification_counts": dict(payload.get("classification_counts", {})),
        "condition_order_summary": {
            "order_evidence_limit": verified["order_evidence_limit"],
            "schedule_variant_counts": [
                {"order": list(order), "trial_count": schedule_counts[order]}
                for order in MODEL_REPLACEMENT_EXECUTION_ORDERS],
            "order_evidence_posture_trial_counts": dict(sorted(
                order_evidence_posture_counts.items())),
            "condition_position_counts_positions_1_to_5":
                verified["condition_position_counts_positions_1_to_5"],
            "condition_outcome_summaries_by_position": grouped,
            "position_effect_estimated": False},
        "claims_posture": payload.get("claims_posture"),
        "non_claims": list(payload.get("non_claims", ())),
        "current_truth": False, "learning_established": False,
        "authority": False}


