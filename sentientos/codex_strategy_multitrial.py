"""Multi-situation orchestration over the canonical operator strategy protocol."""
from __future__ import annotations

import re
import secrets
from typing import Any, Mapping, Sequence

from .embodied_consequence import (OPERATOR_CODEX_STRATEGY_CONDITIONS,
    EmbodiedConsequenceError, build_operator_codex_strategy_packets, canonical_bytes,
    build_operator_codex_strategy_multi_event_packets, digest,
    score_operator_codex_strategy_multi_event_responses,
    score_operator_codex_strategy_responses)


MULTITRIAL_SCORER_SCHEMA = "sentientos.operator_codex_strategy_multitrial_scorer:v1"
MULTITRIAL_PREREG_SCHEMA = "sentientos.operator_codex_strategy_multitrial_preregistration:v1"
_TRIAL_ID = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")


def build_operator_codex_strategy_multitrial(*, writeback: Any,
        trials: Mapping[str, Mapping[str, Any]], model_settings: Mapping[str, Any],
        history_record_id: str | None = None,
        history_record_ids_by_trial: Mapping[str, Sequence[str]] | None = None,
        applicability_by_trial: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
        decision_basis_by_trial: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Freeze at least two distinct situations, each with a full three-condition set."""
    if (not isinstance(trials, Mapping) or not 2 <= len(trials) <= 12
            or any(not isinstance(key, str) or not _TRIAL_ID.fullmatch(key)
                or not isinstance(value, Mapping) for key, value in trials.items())):
        raise EmbodiedConsequenceError("operator_strategy_multitrial_set_invalid")
    if history_record_ids_by_trial is not None:
        if (history_record_id is not None
                or not isinstance(history_record_ids_by_trial, Mapping)
                or set(history_record_ids_by_trial) != set(trials)
                or any(not isinstance(values, (list, tuple)) or not 2 <= len(values) <= 12
                    or any(not isinstance(value, str) or not value for value in values)
                    or len(set(values)) != len(values)
                    for values in history_record_ids_by_trial.values())
                or not isinstance(applicability_by_trial, Mapping)
                or set(applicability_by_trial) != set(trials)
                or (decision_basis_by_trial is not None
                    and (not isinstance(decision_basis_by_trial, Mapping)
                        or set(decision_basis_by_trial) != set(trials)))):
            raise EmbodiedConsequenceError("operator_strategy_multievent_trial_inputs_invalid")
    elif (not isinstance(history_record_id, str) or not history_record_id
            or applicability_by_trial is not None or decision_basis_by_trial is not None):
        raise EmbodiedConsequenceError("operator_strategy_multievent_trial_inputs_invalid")
    situation_digests = {key: digest(value) for key, value in trials.items()}
    bindings = [value.get("situation_binding") for value in trials.values()]
    if len(set(bindings)) != len(bindings) or len(set(situation_digests.values())) != len(trials):
        raise EmbodiedConsequenceError("operator_strategy_multitrial_situations_not_distinct")
    trial_order = list(trials)
    secrets.SystemRandom().shuffle(trial_order)
    prepared: dict[str, dict[str, Any]] = {}
    all_packets: dict[str, dict[str, Any]] = {}
    all_digests: dict[str, str] = {}
    for trial_id in trial_order:
        if history_record_ids_by_trial is None:
            result = build_operator_codex_strategy_packets(writeback=writeback,
                history_record_id=history_record_id, situation=trials[trial_id],
                model_settings=model_settings)
        else:
            result = build_operator_codex_strategy_multi_event_packets(writeback=writeback,
                history_record_ids=history_record_ids_by_trial[trial_id],
                situation=trials[trial_id], model_settings=model_settings,
                applicability_by_event=applicability_by_trial[trial_id],
                decision_basis=(decision_basis_by_trial.get(trial_id)
                    if decision_basis_by_trial is not None else None))
        packet_ids = set(result["subject_packets"])
        if packet_ids & set(all_packets):
            raise EmbodiedConsequenceError("operator_strategy_multitrial_packet_identity_collision")
        prepared[trial_id] = result
        all_packets.update(result["subject_packets"])
        all_digests.update(result["preregistration"]["packet_digests"])
    preregistration = {"schema_version": MULTITRIAL_PREREG_SCHEMA,
        "trial_order": trial_order, "situation_digest_by_trial": situation_digests,
        "trial_preregistration_digest_by_trial": {key: digest(prepared[key]["preregistration"])
            for key in trial_order},
        "packet_order_by_trial": {key: prepared[key]["preregistration"][
            "packet_ids_in_randomized_order"] for key in trial_order},
        "packet_digests": all_digests,
        "model_settings": dict(model_settings),
        "custody_note": "Archive or timestamp this complete preregistration independently before any subject session."}
    scorer_manifest = {"schema_version": MULTITRIAL_SCORER_SCHEMA,
        "trial_order": trial_order,
        "situation_digest_by_trial": situation_digests,
        "trial_preregistration_by_trial": {key: prepared[key]["preregistration"]
            for key in trial_order},
        "scorer_manifest_by_trial": {key: prepared[key]["scorer_manifest"]
            for key in trial_order},
        "subject_packets_by_trial": {key: prepared[key]["subject_packets"]
            for key in trial_order}, "packet_digests": all_digests,
        "model_settings": dict(model_settings),
        "interpretation_limit": "Each situation is scored separately; aggregate counts are descriptive and do not establish statistical significance."}
    return {"subject_packets": all_packets, "scorer_manifest": scorer_manifest,
        "preregistration": preregistration}


def score_operator_codex_strategy_multitrial(*, scorer_manifest: Mapping[str, Any],
        preregistration: Mapping[str, Any], subject_packets: Mapping[str, Mapping[str, Any]],
        responses: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Score each preregistered situation independently and report explicit denominators."""
    if (not isinstance(scorer_manifest, Mapping)
            or set(scorer_manifest) != {"schema_version", "trial_order", "situation_digest_by_trial",
                "trial_preregistration_by_trial", "scorer_manifest_by_trial",
                "subject_packets_by_trial", "packet_digests", "model_settings", "interpretation_limit"}
            or scorer_manifest.get("schema_version") != MULTITRIAL_SCORER_SCHEMA
            or not isinstance(preregistration, Mapping)
            or set(preregistration) != {"schema_version", "trial_order", "situation_digest_by_trial",
                "trial_preregistration_digest_by_trial", "packet_order_by_trial", "packet_digests",
                "model_settings", "custody_note"}
            or preregistration.get("schema_version") != MULTITRIAL_PREREG_SCHEMA
            or not isinstance(responses, Mapping) or not isinstance(subject_packets, Mapping)):
        raise EmbodiedConsequenceError("operator_strategy_multitrial_artifact_invalid")
    order = scorer_manifest.get("trial_order")
    trials = scorer_manifest.get("scorer_manifest_by_trial")
    subregistrations = scorer_manifest.get("trial_preregistration_by_trial")
    packets_by_trial = scorer_manifest.get("subject_packets_by_trial")
    if (not isinstance(order, list) or len(order) < 2 or len(order) > 12
            or len(set(order)) != len(order) or not all(isinstance(x, str) and _TRIAL_ID.fullmatch(x)
                for x in order)
            or not isinstance(trials, Mapping) or set(trials) != set(order)
            or not isinstance(subregistrations, Mapping) or set(subregistrations) != set(order)
            or not isinstance(packets_by_trial, Mapping) or set(packets_by_trial) != set(order)
            or preregistration.get("trial_order") != order
            or preregistration.get("situation_digest_by_trial")
                != scorer_manifest.get("situation_digest_by_trial")
            or preregistration.get("model_settings") != scorer_manifest.get("model_settings")
            or preregistration.get("trial_preregistration_digest_by_trial")
                != {key: digest(subregistrations[key]) for key in order}
            or preregistration.get("packet_order_by_trial") != {key:
                subregistrations[key].get("packet_ids_in_randomized_order") for key in order}
            or preregistration.get("packet_digests") != scorer_manifest.get("packet_digests")):
        raise EmbodiedConsequenceError("operator_strategy_multitrial_preregistration_mismatch")
    packet_map = scorer_manifest.get("packet_digests")
    situation_digests = scorer_manifest.get("situation_digest_by_trial")
    if (not isinstance(packet_map, Mapping) or set(packet_map) != set(subject_packets)
            or not isinstance(situation_digests, Mapping) or set(situation_digests) != set(order)
            or any(digest(subject_packets[key]) != packet_map[key] for key in packet_map)):
        raise EmbodiedConsequenceError("operator_strategy_multitrial_packet_set_mismatch")
    expected_packet_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    session_owners: dict[str, str] = {}
    duplicate_sessions: set[str] = set()
    for packet_id, response in responses.items():
        if packet_id not in packet_map or not isinstance(response, Mapping):
            raise EmbodiedConsequenceError("operator_strategy_multitrial_response_identity_invalid")
        session_id = response.get("session_id")
        if isinstance(session_id, str) and session_id:
            if session_id in session_owners:
                duplicate_sessions.add(session_id)
            session_owners[session_id] = packet_id
    if duplicate_sessions:
        return _aggregate_result(rows=[], task_count=len(order), scored_task_count=0,
            status="not_scored_duplicate_session_across_trials", duplicate_sessions=sorted(duplicate_sessions))
    for trial_id in order:
        trial_packets = packets_by_trial[trial_id]
        if not isinstance(trial_packets, Mapping):
            raise EmbodiedConsequenceError("operator_strategy_multitrial_trial_packets_invalid")
        if (trials[trial_id].get("situation_digest") != situation_digests[trial_id]
                or subregistrations[trial_id].get("situation_digest") != situation_digests[trial_id]
                or trials[trial_id].get("model_settings") != scorer_manifest.get("model_settings")):
            raise EmbodiedConsequenceError("operator_strategy_multitrial_trial_identity_mismatch")
        expected_packet_ids.update(trial_packets)
        trial_responses = {packet_id: responses[packet_id] for packet_id in trial_packets
            if packet_id in responses}
        if trials[trial_id].get("schema_version") == \
                "sentientos.operator_codex_strategy_multi_event_scorer:v1":
            score = score_operator_codex_strategy_multi_event_responses(
                scorer_manifest=trials[trial_id], preregistration=subregistrations[trial_id],
                subject_packets=trial_packets, responses=trial_responses)
            row = {"trial_id": trial_id,
                "situation_digest": scorer_manifest["situation_digest_by_trial"][trial_id],
                "status": score["status"], "outcome": None,
                "submitted_proposal_count": sum(item.get("proposal") is not None
                    for item in score["condition_results"]),
                "condition_count": len(score["condition_results"]),
                "score_digest": score["score_digest"],
                "decision_quality_by_condition": {item["condition"]:
                    item.get("decision_quality", {}).get("criteria")
                    for item in score["condition_results"]},
                "source_event_score": score.get("event_score")}
        else:
            score = score_operator_codex_strategy_responses(scorer_manifest=trials[trial_id],
                preregistration=subregistrations[trial_id], subject_packets=trial_packets,
                responses=trial_responses)
            row = {"trial_id": trial_id,
            "situation_digest": scorer_manifest["situation_digest_by_trial"][trial_id],
            "status": score["strategy_scoring"]["status"],
            "outcome": score["strategy_scoring"].get("outcome"),
            "submitted_proposal_count": score["submitted_proposal_count"],
            "condition_count": len(score["conditions"]), "score_digest": score["score_digest"],
            "conditions": score["conditions"]}
        rows.append(row)
    packet_group_count = sum(len(packets_by_trial[trial_id]) for trial_id in order)
    if expected_packet_ids != set(packet_map) or packet_group_count != len(expected_packet_ids):
        raise EmbodiedConsequenceError("operator_strategy_multitrial_packet_grouping_invalid")
    scored = [row for row in rows if row["status"] == "scored"]
    status = "scored" if len(scored) == len(rows) else "partial_or_incomparable"
    return _aggregate_result(rows=rows, task_count=len(rows), scored_task_count=len(scored),
        status=status, duplicate_sessions=[])


def _aggregate_result(*, rows: list[dict[str, Any]], task_count: int,
        scored_task_count: int, status: str, duplicate_sessions: list[str]) -> dict[str, Any]:
    outcomes = {outcome: sum(row.get("outcome") == outcome for row in rows)
        for outcome in ("stable", "changed", "unsupported")}
    result = {"schema_version": "sentientos.operator_codex_strategy_multitrial_scores:v1",
        "status": status, "task_count": task_count, "scored_task_count": scored_task_count,
        "scoreable_task_fraction": {"numerator": scored_task_count, "denominator": task_count},
        "outcome_counts": outcomes, "trial_results": rows,
        "duplicate_sessions": duplicate_sessions,
        "statistical_significance_claimed": False,
        "subject_session_posture": "operator_reported_external_sessions_not_independently_verified",
        "execution_authority": {"execution_authority": False, "adoption_authority": False}}
    result["score_digest"] = digest(result)
    return result
