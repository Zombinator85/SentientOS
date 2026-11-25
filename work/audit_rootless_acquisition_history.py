"""Create a read-only retrospective audit of one rootless cognition cycle.

This helper validates persisted records, acquisition and completed transfer run
digests, and local invocation receipts. It never creates a model session or
invokes an inference backend.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.developmental_history_intervention_experiment import (  # noqa: E402
    DevelopmentalExperimentStore,
    _digest as experiment_digest,
)
from sentientos.governed_local_model_invocation import validate_receipt  # noqa: E402
from sentientos.local_model_authority import digest_payload  # noqa: E402
from sentientos.local_runtime_provisioning import semantic_digest  # noqa: E402
from sentientos.resident_developmental_cognition import (  # noqa: E402
    ResidentCognitionObservation,
    _history_context_packet,
    _task_family_history_probe_overlap,
    _valid_rootless_epistemic_session_binding,
    audit_task_family_history_projection,
)
from sentientos.resident_developmental_writeback import (  # noqa: E402
    DevelopmentalHistoryStore,
    DevelopmentalRecord,
)
from sentientos.rootless_experimental_ollama_epistemic_session import (  # noqa: E402
    ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_COMPANION_INVOCATION_PURPOSES,
    RootlessExperimentalOllamaEpistemicSession,
)

OBJECTIVE_CONDITION_ORDER = (
    "history_present", "history_withheld", "history_restored")


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("retrospective_audit_json_object_required")
    return value, raw


def _probe_outcome_vector(score: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    """Project per-probe scorer outcomes without retaining model answers."""
    results = score.get("probe_results")
    if not isinstance(results, list):
        return None
    projected: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        if (not isinstance(result, Mapping) or "probe_input" not in result
                or type(result.get("correct")) not in {bool, type(None)}):
            return None
        correct = result["correct"]
        abstained = result.get("abstained", False)
        if (type(abstained) is not bool
                or abstained != (correct is None)):
            return None
        try:
            probe_binding_digest = digest_payload({
                "probe_input": result["probe_input"]})
        except (TypeError, ValueError, UnicodeError, RecursionError):
            return None
        projected.append({"probe_index": index,
            "probe_binding_digest": probe_binding_digest,
            "outcome": "abstained" if abstained else
                "correct" if correct else "incorrect"})
    return projected


def _paired_probe_outcome_summary(score_summaries: Mapping[str, Mapping[str, Any]],
        condition_order: tuple[str, ...]) -> dict[str, Any]:
    """Compare condition outcomes at each probe, preserving unavailable slots."""
    vectors = [score_summaries.get(condition, {}).get("probe_outcomes")
        for condition in condition_order]
    counts = [score_summaries.get(condition, {}).get("probe_count")
        for condition in condition_order]
    complete = (all(isinstance(vector, list) for vector in vectors)
        and len({len(vector) for vector in vectors if isinstance(vector, list)}) == 1
        and all(isinstance(count, int) and type(count) is int
            and count == len(vector)
            for count, vector in zip(counts, vectors)))
    if not complete:
        return {"posture": "probe_level_outcomes_unavailable_or_incomplete",
            "condition_order": list(condition_order),
            "probe_count_by_condition": counts,
            "per_probe": None,
            "paired_outcome_counts": None,
            "evidence_scope": "scorer_correctness_and_abstention_only",
            "response_text_assessed": False,
            "model_attention_assessed": False,
            "learning_established": False,
            "authority": False}
    typed_vectors = [vector for vector in vectors if isinstance(vector, list)]
    per_probe: list[dict[str, Any]] = []
    for index in range(len(typed_vectors[0])):
        outcomes = [vector[index].get("outcome") for vector in typed_vectors]
        if any(vector[index].get("probe_index") != index
                for vector in typed_vectors):
            return {"posture": "probe_level_outcomes_unavailable_or_incomplete",
                "condition_order": list(condition_order),
                "probe_count_by_condition": counts,
                "per_probe": None,
                "paired_outcome_counts": None,
                "evidence_scope": "scorer_correctness_and_abstention_only",
                "response_text_assessed": False,
                "model_attention_assessed": False,
                "learning_established": False,
                "authority": False}
        bindings = [vector[index].get("probe_binding_digest")
            for vector in typed_vectors]
        if len(set(bindings)) != 1:
            return {"posture": "condition_probe_task_binding_mismatch",
                "condition_order": list(condition_order),
                "probe_count_by_condition": counts,
                "per_probe": None,
                "paired_outcome_counts": None,
                "evidence_scope": "scorer_correctness_and_abstention_only",
                "response_text_assessed": False,
                "model_attention_assessed": False,
                "learning_established": False,
                "authority": False}
        per_probe.append({
            "probe_index": index,
            "probe_binding_digest": bindings[0],
            "outcomes_by_condition": dict(zip(condition_order, outcomes)),
            "history_present_vs_withheld": (
                "same" if outcomes[0] == outcomes[1] else "different"),
            "history_present_vs_restored": (
                "same" if outcomes[0] == outcomes[2] else "different"),
        })
    pair_counts: dict[str, dict[str, int]] = {}
    for pair_name, comparison_condition in (
            ("history_present_vs_withheld", condition_order[1]),
            ("history_present_vs_restored", condition_order[2])):
        counts_for_pair = {key: 0 for key in (
            "same_outcome_count", "different_outcome_count",
            "present_correct_comparison_incorrect_count",
            "present_incorrect_comparison_correct_count",
            "abstention_involved_count")}
        for row in per_probe:
            present = row["outcomes_by_condition"][condition_order[0]]
            comparison = row["outcomes_by_condition"][comparison_condition]
            if present == comparison:
                counts_for_pair["same_outcome_count"] += 1
            else:
                counts_for_pair["different_outcome_count"] += 1
            if "abstained" in {present, comparison}:
                counts_for_pair["abstention_involved_count"] += 1
            elif present == "correct" and comparison == "incorrect":
                counts_for_pair[
                    "present_correct_comparison_incorrect_count"] += 1
            elif present == "incorrect" and comparison == "correct":
                counts_for_pair[
                    "present_incorrect_comparison_correct_count"] += 1
        pair_counts[pair_name] = counts_for_pair
    return {"posture": "paired_scorer_outcomes_by_probe_index",
        "condition_order": list(condition_order),
        "probe_count_by_condition": counts,
        "per_probe": per_probe,
        "paired_outcome_counts": pair_counts,
        "evidence_scope": "scorer_correctness_and_abstention_only",
        "response_text_assessed": False,
        "model_attention_assessed": False,
        "learning_established": False,
        "authority": False}


def _offline_receipt_verifier(*, cycle: Mapping[str, Any],
        receipt_root: Path):
    active_identity = cycle.get("active_model_identity")
    if not isinstance(active_identity, Mapping):
        raise ValueError("retrospective_audit_active_model_identity_missing")
    identity = dict(active_identity)
    expected_binding = {
        "run_id": cycle.get("run_id"),
        "preregistration_digest": cycle.get("run_preregistration_digest"),
        "model_manifest_digest": identity.get("model_content_sha256"),
        "runtime_bundle_digest": cycle.get("runtime_observation_digest"),
        "active_model_identity_digest": semantic_digest({"identity": identity}),
    }

    def verify(observation: Mapping[str, Any]) -> Mapping[str, Any]:
        receipt_id = observation.get("inference_receipt_id")
        receipt_digest = observation.get("inference_receipt_digest")
        if not isinstance(receipt_id, str) or not isinstance(receipt_digest, str):
            raise ValueError("retrospective_audit_observation_receipt_missing")
        receipt, _ = _read_json(receipt_root / f"{receipt_id}.json")
        request = receipt.get("request")
        linkage = request.get("linkage") if isinstance(request, Mapping) else None
        binding = (linkage.get("rootless_experimental_session")
            if isinstance(linkage, Mapping) else None)
        if (not isinstance(request, Mapping)
                or not isinstance(linkage, Mapping)
                or not isinstance(binding, Mapping)
                or not _valid_rootless_epistemic_session_binding(binding)
                or request.get("active_model_identity") != identity
                or request.get("request_id") != observation.get("request_id")
                or request.get("request_digest") != observation.get("request_digest")
                or receipt.get("output_digest") != observation.get("output_digest")
                or linkage.get("condition_id") != observation.get("condition_id")
                or linkage.get("history_present") is not (
                    observation.get("condition_id") != "history_withheld")
                or any(binding.get(key) != value
                    for key, value in expected_binding.items())):
            raise ValueError("retrospective_audit_receipt_binding_mismatch")

        verifier = object.__new__(RootlessExperimentalOllamaEpistemicSession)
        verifier.runtime_root = receipt_root.parent
        verifier._allowed_purposes = (
            ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_COMPANION_INVOCATION_PURPOSES)
        verifier.active_model_identity = identity
        verifier.session_binding = dict(binding)
        return verifier.verify_persisted_invocation_receipt(
            receipt_id, receipt_digest,
            expected_request_id=observation.get("request_id"),
            expected_request_digest=observation.get("request_digest"),
            expected_active_model_identity=identity)

    return verify


def _audit_history_intervention_receipts(*, cycle: Mapping[str, Any],
        intervention: Mapping[str, Any], receipt_root: Path) -> dict[str, Any]:
    """Bind intervention condition summaries to their persisted local receipts."""
    conditions = intervention.get("conditions")
    expected_conditions = ("history_present", "history_withheld", "history_restored")
    if (not isinstance(conditions, list) or len(conditions) != 3
            or tuple(row.get("condition_id") if isinstance(row, Mapping) else None
                for row in conditions) != expected_conditions):
        raise ValueError("retrospective_audit_intervention_conditions_invalid")
    active_identity = cycle.get("active_model_identity")
    if not isinstance(active_identity, Mapping):
        raise ValueError("retrospective_audit_intervention_model_identity_missing")
    identity = dict(active_identity)
    files = sorted(receipt_root.glob("*.json"))
    verifier = object.__new__(RootlessExperimentalOllamaEpistemicSession)
    verifier.runtime_root = receipt_root.parent
    verifier._allowed_purposes = (
        ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_COMPANION_INVOCATION_PURPOSES)
    verifier.active_model_identity = identity
    verified_conditions = []
    session_bindings = []
    for condition in conditions:
        prompt_digest = condition.get("prompt_digest")
        expected_prompt_digest = (prompt_digest.removeprefix("sha256:")
            if isinstance(prompt_digest, str) else None)
        matches = []
        for path in files:
            receipt, _ = _read_json(path)
            request = receipt.get("request")
            linkage = request.get("linkage") if isinstance(request, Mapping) else None
            upstream = request.get("upstream_evidence") if isinstance(request, Mapping) else None
            selection = (upstream.get("developmental_history_selection")
                if isinstance(upstream, Mapping) else None)
            selected_records = (selection.get("selected_records")
                if isinstance(selection, Mapping) else None)
            selected_ids = ([row.get("record_id") for row in selected_records]
                if isinstance(selected_records, list)
                    and all(isinstance(row, Mapping) for row in selected_records)
                else None)
            rootless_binding = (linkage.get("rootless_experimental_session")
                if isinstance(linkage, Mapping) else None)
            if (isinstance(request, Mapping) and isinstance(linkage, Mapping)
                    and request.get("purpose") ==
                        "resident_developmental_history_intervention_experiment"
                    and request.get("prompt_digest") == expected_prompt_digest
                    and request.get("active_model_identity") == identity
                    and condition.get("active_model_identity") == identity
                    and linkage.get("condition_id") == condition.get("condition_id")
                    and isinstance(upstream, Mapping)
                    and upstream.get("record_ids") == condition.get(
                        "retrieved_record_ids")
                    and selected_ids == condition.get("retrieved_record_ids")
                    and isinstance(rootless_binding, Mapping)
                    and rootless_binding.get("run_id") == cycle.get("run_id")
                    and receipt.get("output_digest") == condition.get("output_digest")
                    and receipt.get("generation_config") == condition.get(
                        "generation_config")):
                matches.append((path, receipt, request, rootless_binding))
        if len(matches) != 1:
            raise ValueError("retrospective_audit_intervention_receipt_ambiguous")
        path, receipt, request, binding = matches[0]
        valid, _reasons = validate_receipt(receipt)
        if not valid or path.stem != receipt.get("receipt_id"):
            raise ValueError("retrospective_audit_intervention_receipt_invalid")
        expected_binding = {
            "run_id": cycle.get("run_id"),
            "preregistration_digest": cycle.get("run_preregistration_digest"),
            "model_manifest_digest": identity.get("model_content_sha256"),
            "runtime_bundle_digest": cycle.get("runtime_observation_digest"),
            "active_model_identity_digest": semantic_digest({"identity": identity}),
        }
        if (not _valid_rootless_epistemic_session_binding(binding)
                or any(binding.get(key) != value
                    for key, value in expected_binding.items())
                or binding.get("production_authority") is not False
                or binding.get("eligible_as_production_serving_evidence") is not False):
            raise ValueError("retrospective_audit_intervention_session_binding_mismatch")
        verifier.session_binding = dict(binding)
        verified = verifier.verify_persisted_invocation_receipt(
            receipt["receipt_id"], receipt["receipt_digest"],
            expected_request_id=request.get("request_id"),
            expected_request_digest=request.get("request_digest"),
            expected_active_model_identity=identity)
        if (verified.get("output_digest") != condition.get("output_digest")
                or verified["request"].get("prompt_digest") != expected_prompt_digest):
            raise ValueError("retrospective_audit_intervention_receipt_summary_mismatch")
        upstream = request.get("upstream_evidence")
        selection = (upstream.get("developmental_history_selection")
            if isinstance(upstream, Mapping) else None)
        selected_records = (selection.get("selected_records")
            if isinstance(selection, Mapping) else None)
        record_ids = condition.get("retrieved_record_ids")
        record_digests = (upstream.get("record_digests")
            if isinstance(upstream, Mapping) else None)
        if (not isinstance(record_ids, list)
                or not isinstance(record_digests, list)
                or not isinstance(selected_records, list)
                or len(record_ids) != len(record_digests)
                or [row.get("record_id") for row in selected_records
                    if isinstance(row, Mapping)] != record_ids
                or [row.get("record_digest") for row in selected_records
                    if isinstance(row, Mapping)] != record_digests
                or (condition["condition_id"] == "history_withheld"
                    and selection.get("treatment") != "withheld")
                or (condition["condition_id"] != "history_withheld"
                    and selection.get("treatment") != "present")
                or condition.get("developmental_projection_present") is not bool(record_ids)):
            raise ValueError("retrospective_audit_intervention_history_selection_mismatch")
        verified_record_refs = []
        for record_id, record_digest in zip(record_ids, record_digests):
            if (not isinstance(record_id, str)
                    or re.fullmatch(r"devrec-[0-9a-f]{24}", record_id) is None):
                raise ValueError("retrospective_audit_intervention_record_id_invalid")
            record_path = (receipt_root.parent.parent / "resident-cognition"
                / "history" / "records" / f"{record_id}.json")
            record_json, _record_raw = _read_json(record_path)
            record = DevelopmentalRecord(**record_json)
            DevelopmentalHistoryStore._verify_record(record)
            if record.record_id != record_id or record.record_digest != record_digest:
                raise ValueError("retrospective_audit_intervention_record_digest_mismatch")
            verified_record_refs.append({"record_id": record_id,
                "record_digest": record_digest})
        session_bindings.append(dict(binding))
        verified_conditions.append({
            "condition_id": condition["condition_id"],
            "receipt_id": receipt["receipt_id"],
            "receipt_digest": receipt["receipt_digest"],
            "receipt_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "prompt_digest": prompt_digest,
            "output_digest": receipt["output_digest"],
            "retrieved_record_ids": condition.get("retrieved_record_ids"),
            "developmental_projection_present": condition.get(
                "developmental_projection_present"),
            "owner_verified_history_records": verified_record_refs,
        })
    present, withheld, restored = verified_conditions
    replay_claim = intervention.get("same_history_replay")
    common_session_verified = (
        len({json.dumps(binding, sort_keys=True) for binding in session_bindings}) == 1)
    common_model_identity = all(
        condition.get("active_model_identity") == identity for condition in conditions)
    common_generation_config = all(
        condition.get("generation_config") == conditions[0].get("generation_config")
        for condition in conditions[1:])
    replay_verified = (
        present["prompt_digest"] == restored["prompt_digest"]
        and present["output_digest"] == restored["output_digest"]
        and conditions[0].get("active_model_identity") == identity
        and conditions[2].get("active_model_identity") == identity
        and conditions[0].get("generation_config")
            == conditions[2].get("generation_config"))
    present_selection = present["retrieved_record_ids"]
    withheld_selection = withheld["retrieved_record_ids"]
    restored_selection = restored["retrieved_record_ids"]
    return {
        "status": "three_condition_receipts_verified",
        "receipt_and_prompt_output_bindings_verified": True,
        "receipt_history_selection_and_record_bindings_verified": True,
        "common_session_binding_verified": common_session_verified,
        "common_model_identity_verified": common_model_identity,
        "common_generation_config_verified": common_generation_config,
        "condition_receipts": verified_conditions,
        "history_present_withheld_prompt_differs": (
            present["prompt_digest"] != withheld["prompt_digest"]),
        "history_present_restored_prompt_matches": (
            present["prompt_digest"] == restored["prompt_digest"]),
        "history_present_withheld_output_differs": (
            present["output_digest"] != withheld["output_digest"]),
        "history_present_restored_output_matches": (
            present["output_digest"] == restored["output_digest"]),
        "history_withheld_selection_empty": withheld_selection == [],
        "history_present_restored_selection_matches": (
            present_selection == restored_selection),
        "same_history_replay_claim_verified": replay_verified
            and isinstance(replay_claim, Mapping)
            and replay_claim.get("active_model_identity_matches") is True
            and replay_claim.get("generation_config_matches") is True
            and replay_claim.get("output_digest_matches") is True
            and replay_claim.get("prompt_digest_matches") is True,
        "inference_performed": False,
        "learning_claim_made": False,
    }


def _audit_later_companion_decision(*, cycle: Mapping[str, Any],
        receipt_root: Path, intervention_audit: Mapping[str, Any]) -> dict[str, Any]:
    """Compare accepted response content separately from history citations."""
    decision = cycle.get("later_companion_decision_intervention")
    expected_order = ("history_present", "history_withheld", "history_restored")
    if not isinstance(decision, Mapping):
        return {"status": "not_present", "history_changed_cognition": None,
            "learning_claim_made": False}
    rows = decision.get("conditions")
    receipt_rows = intervention_audit.get("condition_receipts")
    semantic_decisions = decision.get("semantic_decisions")
    if (not isinstance(rows, list) or len(rows) != 3
            or not isinstance(receipt_rows, list) or len(receipt_rows) != 3
            or not isinstance(semantic_decisions, list)
            or len(semantic_decisions) != 3
            or tuple(row.get("condition_id") if isinstance(row, Mapping) else None
                for row in rows) != expected_order
            or tuple(row.get("condition_id") if isinstance(row, Mapping) else None
                for row in semantic_decisions) != expected_order):
        raise ValueError("retrospective_audit_companion_decision_conditions_invalid")
    raw_by_condition: dict[str, dict[str, Any]] = {}
    summary_rows = []
    for row, receipt_summary, semantic_row in zip(rows, receipt_rows,
            semantic_decisions):
        if (not isinstance(row, Mapping)
                or row.get("condition_id") != receipt_summary.get("condition_id")
                or row.get("inference_receipt_id") != receipt_summary.get("receipt_id")
                or row.get("inference_receipt_digest") != receipt_summary.get(
                    "receipt_digest")
                or row.get("output_digest") != receipt_summary.get("output_digest")
                or row.get("prompt_digest") != receipt_summary.get("prompt_digest")
                or row.get("retrieved_record_ids") != receipt_summary.get(
                    "retrieved_record_ids")
                or semantic_row.get("decision_validation_status") != row.get(
                    "decision_validation_status", "validated")
                or semantic_row.get("decision_validation_error_code") != row.get(
                    "decision_validation_error_code")):
            raise ValueError("retrospective_audit_companion_decision_receipt_binding_mismatch")
        receipt, _ = _read_json(receipt_root / f"{receipt_summary['receipt_id']}.json")
        valid, _reasons = validate_receipt(receipt)
        if (not valid or receipt.get("receipt_digest") != receipt_summary.get(
                "receipt_digest") or receipt.get("output_digest") != row.get(
                    "output_digest")):
            raise ValueError("retrospective_audit_companion_decision_receipt_invalid")
        try:
            raw_output = json.loads(receipt.get("output_text", ""))
        except (TypeError, ValueError):
            raise ValueError("retrospective_audit_companion_decision_output_invalid")
        if not isinstance(raw_output, Mapping):
            raise ValueError("retrospective_audit_companion_decision_output_invalid")
        raw_by_condition[row["condition_id"]] = dict(raw_output)
        selected_ids = row.get("retrieved_record_ids")
        citations = raw_output.get("history_record_ids")
        citations_compatible = (isinstance(citations, list)
            and all(isinstance(item, str) for item in citations)
            and len(set(citations)) == len(citations)
            and isinstance(selected_ids, list)
            and set(citations).issubset(selected_ids)
            and (row["condition_id"] != "history_withheld" or not citations))
        raw_response = raw_output.get("response")
        response_digest = (digest_payload({"text": raw_response})
            if isinstance(raw_response, str) else None)
        non_citation_digest = digest_payload({key: value
            for key, value in raw_output.items() if key != "history_record_ids"})
        status = row.get("decision_validation_status", "validated")
        if status == "validated":
            if (row.get("response") != raw_response
                    or row.get("response_digest") != response_digest
                    or row.get("disposition") != raw_output.get("disposition")
                    or row.get("history_record_ids") != citations
                    or not citations_compatible):
                raise ValueError("retrospective_audit_admitted_decision_binding_mismatch")
        elif status == "rejected_invalid_output":
            recorded_raw_digest = semantic_row.get("rejected_raw_response_digest")
            if ((recorded_raw_digest is not None
                    and recorded_raw_digest != response_digest)
                    or semantic_row.get("history_citation_bound") is not False
                    or citations_compatible
                    or row.get("response") != "INVALID_EXPERIMENTAL_RESPONSE"
                    or row.get("disposition") != "abstain"):
                raise ValueError("retrospective_audit_rejected_decision_diagnostic_mismatch")
        else:
            raise ValueError("retrospective_audit_decision_status_invalid")
        summary_rows.append({
            "condition_id": row["condition_id"],
            "decision_validation_status": status,
            "decision_validation_error_code": row.get(
                "decision_validation_error_code"),
            "raw_response_digest": response_digest,
            "non_citation_output_digest": non_citation_digest,
            "raw_history_citation_count": len(citations) if isinstance(citations, list) else None,
            "history_citations_match_selected_records": citations_compatible,
        })
    response_digests = [item["raw_response_digest"] for item in summary_rows]
    content_digests = [item["non_citation_output_digest"] for item in summary_rows]
    response_unchanged = len(set(response_digests)) == 1
    non_citation_output_unchanged = len(set(content_digests)) == 1
    history_changed_cognition = not non_citation_output_unchanged
    if decision.get("history_changed_cognition") is not history_changed_cognition:
        raise ValueError("retrospective_audit_cognition_change_classification_mismatch")
    return {
        "status": "three_condition_decisions_bound_to_verified_receipts",
        "condition_decisions": summary_rows,
        "response_content_matches_across_conditions": response_unchanged,
        "non_citation_output_matches_across_conditions": non_citation_output_unchanged,
        "history_citation_only_output_difference": (
            non_citation_output_unchanged
            and len({row.get("output_digest") for row in rows}) > 1),
        "history_changed_cognition": history_changed_cognition,
        "reported_semantic_decision_classification": decision.get(
            "semantic_decision_classification"),
        "reported_response_text_classification": decision.get(
            "response_text_classification"),
        "performance_improvement_established": decision.get(
            "performance_improvement_established") is True,
        "learning_claim_made": decision.get("causal_or_learning_claim_made") is True,
    }


def _audit_legacy_transfer_projection_delivery(*,
        task_family_id: str, transfer_descriptor: Mapping[str, Any],
        transfer_conditions: list[Any], cycle_transfer_conditions: list[Any],
        receipt_verifier: Any, history_store: DevelopmentalHistoryStore
        ) -> dict[str, Any]:
    """Audit v18 receipt projections whose cycle summaries lack newer evidence.

    This verifies the task-family projection metadata and selected record
    references delivered in the verified request envelope. It does not rebuild
    raw prompt text or infer model attention.
    """
    conditions = set(OBJECTIVE_CONDITION_ORDER)
    run_rows = {row.get("condition_id"): row for row in transfer_conditions
        if isinstance(row, Mapping)}
    cycle_rows = {row.get("condition_id"): row for row in cycle_transfer_conditions
        if isinstance(row, Mapping)}
    if set(run_rows) != conditions or set(cycle_rows) != conditions:
        return {"status": "condition_rows_incomplete",
            "condition_receipt_refs_bound": False,
            "projection_prompt_digest_bound": False,
            "selected_history_record_refs_reloaded": False,
            "exact_prompt_serialization_reconstructed": False,
            "model_attention_established": False,
            "authority": False}
    task_digest = transfer_descriptor.get("task_digest")
    task_probe_count = transfer_descriptor.get("probe_count")
    if (not isinstance(task_digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", task_digest) is None
            or type(task_probe_count) is not int or task_probe_count <= 0):
        raise ValueError("retrospective_audit_legacy_projection_task_binding_invalid")
    condition_reports: dict[str, Any] = {}
    for condition in OBJECTIVE_CONDITION_ORDER:
        run_row, cycle_row = run_rows[condition], cycle_rows[condition]
        if (run_row.get("inference_receipt_id") != cycle_row.get(
                    "inference_receipt_id")
                or run_row.get("inference_receipt_digest") != cycle_row.get(
                    "inference_receipt_digest")
                or run_row.get("output_digest") != cycle_row.get("output_digest")
                or run_row.get("retrieved_record_ids") != cycle_row.get(
                    "retrieved_record_ids")):
            raise ValueError(
                "retrospective_audit_legacy_projection_cycle_run_binding_mismatch")
        try:
            receipt = receipt_verifier(run_row)
        except Exception as exc:
            raise ValueError(
                "retrospective_audit_legacy_projection_receipt_invalid") from exc
        request = receipt.get("request") if isinstance(receipt, Mapping) else None
        upstream = (request.get("upstream_evidence")
            if isinstance(request, Mapping) else None)
        projection = (upstream.get("task_family_history_prompt_projection")
            if isinstance(upstream, Mapping) else None)
        selection = (upstream.get("developmental_history_selection")
            if isinstance(upstream, Mapping) else None)
        if (not isinstance(request, Mapping) or not isinstance(upstream, Mapping)
                or not isinstance(projection, Mapping)
                or not isinstance(selection, Mapping)):
            raise ValueError(
                "retrospective_audit_legacy_projection_request_evidence_missing")
        projection_semantic = dict(projection)
        projection_digest = projection_semantic.pop("projection_digest", None)
        condition_treatment = ("withheld" if condition == "history_withheld"
            else "present")
        if (projection.get("schema_version") !=
                    "sentientos.task_family_history_prompt_projection:v18"
                or not isinstance(projection_digest, str)
                or projection_digest != "sha256:" + digest_payload(
                    projection_semantic)
                or projection.get("condition_id") != condition
                or projection.get("treatment") != condition_treatment
                or projection.get("task_family_id") != task_family_id
                or projection.get("prompt_binding_posture") !=
                    "exact_governed_request_prompt_digest"
                or projection.get("governed_request_prompt_digest") !=
                    request.get("prompt_digest")
                or upstream.get("objective_task_digest") != task_digest
                or upstream.get("task_family_id") != task_family_id):
            raise ValueError(
                "retrospective_audit_legacy_projection_binding_invalid")
        retrieved_ids = run_row.get("retrieved_record_ids")
        retrieved_digests = run_row.get("retrieved_record_digests")
        upstream_ids, upstream_digests = (upstream.get("record_ids"),
            upstream.get("record_digests"))
        selected = selection.get("selected_records")
        if (not isinstance(retrieved_ids, list)
                or not isinstance(retrieved_digests, list)
                or len(retrieved_ids) != len(retrieved_digests)
                or upstream_ids != retrieved_ids
                or upstream_digests != retrieved_digests
                or not isinstance(selected, list)
                or [(row.get("record_id"), row.get("record_digest"))
                    for row in selected if isinstance(row, Mapping)]
                    != list(zip(retrieved_ids, retrieved_digests))
                or len(selected) != len(retrieved_ids)):
            raise ValueError(
                "retrospective_audit_legacy_projection_selected_refs_invalid")
        for record_id, record_digest in zip(retrieved_ids, retrieved_digests):
            record = history_store.get(record_id)
            if record.record_digest != record_digest:
                raise ValueError(
                    "retrospective_audit_legacy_projection_record_digest_mismatch")
        projection_records = projection.get("records")
        zero_counts = (
            projection.get("task_relevant_record_count") == 0
            and projection.get("task_relevant_example_count") == 0
            and projection.get("prior_incorrect_example_count") == 0
            and projection.get("prior_abstained_example_count") == 0
            and projection.get("candidate_integer_affine_strategy_count") == 0
            and projection.get("accumulated_candidate_integer_affine_strategy") is None)
        if (not isinstance(projection_records, list)
                or projection_records
                or projection.get("task_relevant_record_count") != len(
                    projection_records)
                or not zero_counts
                or (condition == "history_withheld" and retrieved_ids)):
            raise ValueError(
                "retrospective_audit_legacy_projection_content_invalid")
        condition_reports[condition] = {
            "receipt_digest": run_row.get("inference_receipt_digest"),
            "projection_digest": projection_digest,
            "projection_schema_version": projection.get("schema_version"),
            "projection_prompt_digest_bound": True,
            "selected_history_record_count": len(retrieved_ids),
            "task_relevant_record_count": 0,
            "task_relevant_example_count": 0,
            "task_family_strategy_present": False,
            "selected_history_records_reloaded": True,
            "authority": False,
        }
    return {"status": "verified_zero_task_family_material_in_projection",
        "condition_evidence": condition_reports,
        "condition_receipt_refs_bound": True,
        "projection_prompt_digest_bound": True,
        "selected_history_record_refs_reloaded": True,
        "exact_prompt_serialization_reconstructed": False,
        "model_attention_established": False,
        "learning_established": False,
        "authority": False}


def _audit_transfer_projection_delivery_v5(*, task_family_id: str,
        transfer_descriptor: Mapping[str, Any], transfer_conditions: list[Any],
        cycle_transfer_conditions: list[Any], receipt_verifier: Any,
        history_store: DevelopmentalHistoryStore) -> dict[str, Any]:
    """Rebind v5 delivery summaries to exact persisted requests and records.

    This is a receipt/projection audit only. The ephemeral prompt text is not
    persisted, so it cannot establish exact prompt serialization or attention.
    """
    expected_conditions = set(OBJECTIVE_CONDITION_ORDER)
    run_rows = {row.get("condition_id"): row for row in transfer_conditions
        if isinstance(row, Mapping)}
    cycle_rows = {row.get("condition_id"): row
        for row in cycle_transfer_conditions if isinstance(row, Mapping)}
    if set(run_rows) != expected_conditions or set(cycle_rows) != expected_conditions:
        raise ValueError("retrospective_audit_transfer_v5_conditions_incomplete")
    task_digest = transfer_descriptor.get("task_digest")
    if not isinstance(task_digest, str) or not task_digest:
        raise ValueError("retrospective_audit_transfer_v5_task_binding_invalid")

    condition_evidence: dict[str, Any] = {}
    for condition in OBJECTIVE_CONDITION_ORDER:
        run_row, cycle_row = run_rows[condition], cycle_rows[condition]
        evidence = cycle_row.get("task_family_prompt_delivery_evidence")
        if (not isinstance(evidence, Mapping)
                or evidence.get("schema_version") !=
                    "sentientos.objective_task_family_prompt_delivery_evidence:v5"
                or evidence.get("status") !=
                    "verified_projection_bound_to_governed_request"
                or evidence.get("condition_id") != condition
                or evidence.get("treatment") != (
                    "withheld" if condition == "history_withheld" else "present")
                or evidence.get("claim_scope") !=
                    "request_projection_binding_not_model_attention_or_learning"
                or evidence.get("raw_prompt_included") is not False
                or evidence.get("answer_values_included") is not False
                or cycle_row.get("inference_receipt_id") !=
                    run_row.get("inference_receipt_id")
                or cycle_row.get("inference_receipt_digest") !=
                    run_row.get("inference_receipt_digest")
                or cycle_row.get("output_digest") != run_row.get("output_digest")
                or cycle_row.get("retrieved_record_ids") !=
                    run_row.get("retrieved_record_ids")):
            raise ValueError(
                "retrospective_audit_transfer_v5_cycle_run_binding_invalid")
        try:
            receipt = receipt_verifier(run_row)
        except Exception as exc:
            raise ValueError(
                "retrospective_audit_transfer_v5_receipt_invalid") from exc
        request = receipt.get("request") if isinstance(receipt, Mapping) else None
        upstream = request.get("upstream_evidence") if isinstance(
            request, Mapping) else None
        projection = (upstream.get("task_family_history_prompt_projection")
            if isinstance(upstream, Mapping) else None)
        selection = (upstream.get("developmental_history_selection")
            if isinstance(upstream, Mapping) else None)
        if not all(isinstance(value, Mapping) for value in
                (request, upstream, projection, selection)):
            raise ValueError(
                "retrospective_audit_transfer_v5_request_projection_missing")

        projection_semantic = dict(projection)
        projection_digest = projection_semantic.pop("projection_digest", None)
        selection_semantic = dict(selection)
        selection_digest = selection_semantic.pop("selection_digest", None)
        request_digest = request.get("request_digest")
        prompt_digest = request.get("prompt_digest")
        selected = selection.get("selected_records")
        selected_refs = ([(item.get("record_id"), item.get("record_digest"))
            for item in selected if isinstance(item, Mapping)]
            if isinstance(selected, list) else None)
        retrieved_ids = run_row.get("retrieved_record_ids")
        retrieved_digests = run_row.get("retrieved_record_digests")
        if (not isinstance(projection_digest, str)
                or projection_digest != "sha256:" + digest_payload(
                    projection_semantic)
                or not isinstance(selection_digest, str)
                or selection_digest != "sha256:" + digest_payload(
                    selection_semantic)
                or evidence.get("projection_digest") != projection_digest
                or evidence.get("request_id") != request.get("request_id")
                or evidence.get("request_digest") != request_digest
                or evidence.get("inference_prompt_digest") != prompt_digest
                or projection.get("governed_request_prompt_digest") != prompt_digest
                or projection.get("condition_id") != condition
                or projection.get("task_family_id") != task_family_id
                or upstream.get("objective_task_digest") != task_digest
                or upstream.get("task_family_id") != task_family_id
                or selection.get("selection_digest") != evidence.get(
                    "history_selection_digest")
                or evidence.get("history_selection_digest_recomputed") is not True
                or not isinstance(retrieved_ids, list)
                or not isinstance(retrieved_digests, list)
                or selected_refs != list(zip(retrieved_ids, retrieved_digests))
                or upstream.get("record_ids") != retrieved_ids
                or upstream.get("record_digests") != retrieved_digests
                or evidence.get("selected_record_count") != len(retrieved_ids)
                or projection.get("selected_record_count") != len(retrieved_ids)
                or (condition == "history_withheld" and retrieved_ids)):
            raise ValueError(
                "retrospective_audit_transfer_v5_projection_binding_invalid")
        for record_id, record_digest in zip(retrieved_ids, retrieved_digests):
            record = history_store.get(record_id)
            if record.record_digest != record_digest:
                raise ValueError(
                    "retrospective_audit_transfer_v5_record_digest_mismatch")

        condition_evidence[condition] = {
            "receipt_id": run_row.get("inference_receipt_id"),
            "receipt_digest": run_row.get("inference_receipt_digest"),
            "request_id": request.get("request_id"),
            "request_digest": request_digest,
            "projection_digest": projection_digest,
            "selection_digest": selection_digest,
            "selected_history_record_count": len(retrieved_ids),
            "selected_history_record_refs_reloaded": True,
            "condition_request_projection_binding_verified": True,
            "authority": False,
        }
    return {
        "status": "verified_v5_request_projection_and_history_refs",
        "condition_evidence": condition_evidence,
        "condition_receipt_refs_bound": True,
        "projection_prompt_digest_bound": True,
        "selected_history_record_refs_reloaded": True,
        "exact_prompt_serialization_reconstructed": False,
        "model_attention_established": False,
        "learning_established": False,
        "authority": False,
    }


def _audit_acquisition_source_run(*, run_id: str, cycle_root: Path,
        experiment_store: DevelopmentalExperimentStore,
        record: DevelopmentalRecord, task_family_id: str,
        target_model_identity: Mapping[str, Any], facts: Any) -> dict[str, Any]:
    """Verify one acquisition run and its independent score binding."""
    if re.fullmatch(r"devexp-run-[0-9a-f]{24}", run_id) is None:
        raise ValueError("retrospective_audit_source_run_id_invalid")
    run_path = (cycle_root / "resident-cognition" / "state"
        / "developmental_experiments" / "runs" / f"{run_id}.json")
    run, run_raw = _read_json(run_path)
    run_semantic = {key: value for key, value in run.items()
        if key not in {"run_id", "run_digest"}}
    run_digest = experiment_digest(run_semantic)
    if run.get("run_id") != run_id or run.get("run_digest") != run_digest:
        raise ValueError("retrospective_audit_run_digest_mismatch")
    if experiment_store.load_run(run_id) != run:
        raise ValueError("retrospective_audit_verified_run_mismatch")

    scores = run.get("objective_scores")
    conditions = run.get("conditions")
    if (not isinstance(scores, list) or len(scores) != 3
            or not isinstance(conditions, list) or len(conditions) != 3):
        raise ValueError("retrospective_audit_acquisition_conditions_incomplete")
    score_summaries: dict[str, dict[str, Any]] = {}
    for row in scores:
        if (not isinstance(row, Mapping) or row.get("condition_id") not in {
                "history_present", "history_withheld", "history_restored"}
                or row["condition_id"] in score_summaries):
            raise ValueError("retrospective_audit_score_row_invalid")
        score = row.get("score")
        if not isinstance(score, Mapping):
            raise ValueError("retrospective_audit_score_missing")
        score_summaries[row["condition_id"]] = {
            "status": score.get("status"),
            "correct_count": score.get("correct_count"),
            "probe_count": score.get("probe_count"),
            "score_digest": score.get("score_digest"),
            "probe_outcomes": _probe_outcome_vector(score),
        }
    if set(score_summaries) != set(OBJECTIVE_CONDITION_ORDER):
        raise ValueError("retrospective_audit_acquisition_conditions_incomplete")

    projection_audit = audit_task_family_history_projection(
        record.candidate, task_family_id=task_family_id,
        target_model_identity=target_model_identity, source_run_id=run_id)
    source_projection = projection_audit.get("source_run_score_projection")
    history_score = score_summaries["history_present"]
    per_experience_binding = (
        isinstance(source_projection, Mapping)
        and source_projection.get("source_score_digests")
            == [history_score.get("score_digest")]
        and source_projection.get("example_count")
            == history_score.get("probe_count")
        and source_projection.get("correct_example_count")
            == history_score.get("correct_count"))

    aggregate_facts = []
    for fact in facts if isinstance(facts, (list, tuple)) else ():
        payload = fact.get("payload") if isinstance(fact, Mapping) else None
        if (isinstance(payload, Mapping) and payload.get("run_id") == run_id
                and payload.get("objective_task_family") == task_family_id):
            aggregate_facts.append(payload)
    aggregate_binding = False
    if len(aggregate_facts) == 1:
        payload = aggregate_facts[0]
        payload_evaluation = payload.get("objective_evaluation")
        payload_scores = payload.get("objective_scores")
        run_evaluation = run.get("objective_evaluation")
        if (isinstance(payload_evaluation, Mapping)
                and isinstance(run_evaluation, Mapping)
                and isinstance(payload_scores, list)
                and payload.get("run_digest") == run_digest
                and payload_evaluation.get("plan_digest")
                    == run_evaluation.get("plan_digest")
                and payload_evaluation.get("probe_count") == 3
                and len(payload_scores) == 3):
            payload_by_condition = {row.get("condition_id"): row
                for row in payload_scores if isinstance(row, Mapping)}
            aggregate_binding = (
                set(payload_by_condition) == set(score_summaries)
                and all(payload_by_condition[condition].get("score_digest")
                        == summary.get("score_digest")
                    and payload_by_condition[condition].get("correct_count")
                        == summary.get("correct_count")
                    and payload_by_condition[condition].get("probe_count")
                        == summary.get("probe_count")
                    and payload_by_condition[condition].get("status")
                        == summary.get("status")
                    for condition, summary in score_summaries.items())
                and payload_evaluation.get("condition_score_digests") == [
                    score_summaries[condition]["score_digest"]
                    for condition in OBJECTIVE_CONDITION_ORDER])
    score_binding = per_experience_binding or aggregate_binding
    return {
        "run_id": run_id,
        "run_digest": run_digest,
        "run_file_sha256": hashlib.sha256(run_raw).hexdigest(),
        "owner_run_reload_verified": True,
        "history_record_score_binding_verified": score_binding,
        "history_record_score_binding_method": (
            "per_experience_projection" if per_experience_binding else
            "legacy_aggregate_trial_fact" if aggregate_binding else
            "unverified"),
        "condition_score_summaries": score_summaries,
        "paired_probe_outcome_summary": _paired_probe_outcome_summary(
            score_summaries, OBJECTIVE_CONDITION_ORDER),
    }


def create_audit(*, cycle_root: Path, output_path: Path) -> dict[str, Any]:
    cycle_root = cycle_root.resolve(strict=True)
    cycle_path = cycle_root / "cycle-result.json"
    cycle, cycle_raw = _read_json(cycle_path)
    transfer = cycle.get("objective_task_family_transfer")
    if not isinstance(transfer, Mapping):
        raise ValueError("retrospective_audit_transfer_summary_missing")
    record_id = transfer.get(
        "acquisition_history_record_id")
    if not isinstance(record_id, str) or not record_id:
        raise ValueError("retrospective_audit_acquisition_record_missing")
    record_path = (cycle_root / "resident-cognition" / "history" / "records"
        / f"{record_id}.json")
    record_json, record_raw = _read_json(record_path)
    record = DevelopmentalRecord(**record_json)
    DevelopmentalHistoryStore._verify_record(record)
    if record.record_id != record_id:
        raise ValueError("retrospective_audit_record_id_mismatch")

    facts = record.candidate.get("selected_facts", ())
    source_runs = set()
    source_families = set()
    supported_families = {
        "rootless_integer_affine_transfer_low_range_v5",
        "rootless_integer_affine_transfer_low_range_v6",
    }
    for fact in facts if isinstance(facts, (list, tuple)) else ():
        payload = fact.get("payload") if isinstance(fact, Mapping) else None
        if (isinstance(payload, Mapping)
                and isinstance(payload.get("objective_task_family"), str)
                and payload.get("objective_task_family") in supported_families
                and isinstance(payload.get("run_id"), str)):
            source_runs.add(payload["run_id"])
            source_families.add(payload["objective_task_family"])
    task_family_id = transfer.get("task_family_id")
    if task_family_id is None and len(source_families) == 1:
        task_family_id = next(iter(source_families))
    if (not isinstance(task_family_id, str)
            or task_family_id not in supported_families
            or source_families != {task_family_id}):
        raise ValueError("retrospective_audit_task_family_binding_invalid")
    if not source_runs:
        raise ValueError("retrospective_audit_source_run_missing")
    receipt_root = cycle_root / "inference-custody" / "receipts"
    history_store = DevelopmentalHistoryStore(
        cycle_root / "resident-cognition" / "history")
    receipt_verifier = _offline_receipt_verifier(
        cycle=cycle, receipt_root=receipt_root)
    experiment_store = DevelopmentalExperimentStore(
        cycle_root / "resident-cognition" / "state",
        invocation_verifier=receipt_verifier)
    acquisition_runs = [
        _audit_acquisition_source_run(run_id=run_id, cycle_root=cycle_root,
            experiment_store=experiment_store, record=record,
            task_family_id=task_family_id,
            target_model_identity=cycle["active_model_identity"], facts=facts)
        for run_id in sorted(source_runs)]
    source_score_binding_verified = all(
        row["history_record_score_binding_verified"]
        for row in acquisition_runs)
    score_binding_methods = {row["history_record_score_binding_method"]
        for row in acquisition_runs}
    if source_score_binding_verified and score_binding_methods == {
            "per_experience_projection"}:
        score_binding_method = "per_experience_projection"
    elif source_score_binding_verified and score_binding_methods == {
            "legacy_aggregate_trial_fact"}:
        score_binding_method = "legacy_aggregate_trial_fact"
    elif source_score_binding_verified:
        score_binding_method = "mixed_per_run_verified_bindings"
    else:
        score_binding_method = "one_or_more_source_runs_unverified"
    audit = audit_task_family_history_projection(record.candidate,
        task_family_id=task_family_id,
        target_model_identity=cycle["active_model_identity"])

    transfer_run_audit: dict[str, Any] = {
        "status": "not_present",
        "owner_run_reload_verified": False,
        "condition_summary_binding_verified": False,
        "inference_performed": False,
    }
    transfer_projection_delivery_audit: dict[str, Any] = {
        "status": "not_present",
        "condition_receipt_refs_bound": False,
        "projection_prompt_digest_bound": False,
        "selected_history_record_refs_reloaded": False,
        "exact_prompt_serialization_reconstructed": False,
        "model_attention_established": False,
        "learning_established": False,
        "authority": False,
    }
    transfer_run_id = transfer.get("run_id")
    if transfer_run_id is not None:
        if (not isinstance(transfer_run_id, str)
                or re.fullmatch(r"devexp-run-[0-9a-f]{24}", transfer_run_id) is None):
            raise ValueError("retrospective_audit_transfer_run_id_invalid")
        transfer_run_path = (cycle_root / "resident-cognition" / "state"
            / "developmental_experiments" / "runs" / f"{transfer_run_id}.json")
        transfer_run, transfer_run_raw = _read_json(transfer_run_path)
        transfer_run_semantic = {key: value for key, value in transfer_run.items()
            if key not in {"run_id", "run_digest"}}
        transfer_run_digest = experiment_digest(transfer_run_semantic)
        if (transfer_run.get("run_id") != transfer_run_id
                or transfer_run.get("run_digest") != transfer_run_digest
                or transfer.get("run_digest") != transfer_run_digest):
            raise ValueError("retrospective_audit_transfer_run_digest_mismatch")
        verified_transfer_run = experiment_store.load_run(transfer_run_id)
        if verified_transfer_run != transfer_run:
            raise ValueError("retrospective_audit_verified_transfer_run_mismatch")
        transfer_scores = transfer_run.get("objective_scores")
        transfer_conditions = transfer_run.get("conditions")
        if (not isinstance(transfer_scores, list) or len(transfer_scores) != 3
                or not isinstance(transfer_conditions, list)
                or len(transfer_conditions) != 3):
            raise ValueError("retrospective_audit_transfer_conditions_incomplete")
        transfer_score_summaries = {}
        for row in transfer_scores:
            if (not isinstance(row, Mapping) or row.get("condition_id") not in {
                    "history_present", "history_withheld", "history_restored"}
                    or not isinstance(row.get("score"), Mapping)):
                raise ValueError("retrospective_audit_transfer_score_row_invalid")
            score = row["score"]
            transfer_score_summaries[row["condition_id"]] = {
                "status": score.get("status"),
                "correct_count": score.get("correct_count"),
                "probe_count": score.get("probe_count"),
                "score_digest": score.get("score_digest"),
                "probe_outcomes": _probe_outcome_vector(score),
            }
        expected_transfer_counts = transfer.get("condition_correct_counts")
        observed_transfer_counts = [transfer_score_summaries.get(condition, {}).get(
            "correct_count") for condition in (
                "history_present", "history_withheld", "history_restored")]
        transfer_protocol = transfer_run.get("protocol")
        transfer_descriptor = (transfer_protocol.get("objective_task_descriptor")
            if isinstance(transfer_protocol, Mapping) else None)
        if (transfer.get("task_family_id") != task_family_id
                or not isinstance(transfer_descriptor, Mapping)
                or transfer_descriptor.get("task_family_id") != task_family_id
                or expected_transfer_counts != observed_transfer_counts):
            raise ValueError("retrospective_audit_transfer_summary_binding_mismatch")
        # Recompute exact probe overlap from verified selected records and bind
        # the resulting measures to each receipt and the owner-verified run.
        # Raw prompt text is deliberately not persisted, so this still does
        # not reconstruct exact prompt serialization.
        cycle_transfer_conditions = transfer.get("conditions")
        condition_rows = {row.get("condition_id"): row
            for row in transfer_conditions if isinstance(row, Mapping)}
        cycle_condition_rows = {row.get("condition_id"): row
            for row in cycle_transfer_conditions if isinstance(row, Mapping)} \
            if isinstance(cycle_transfer_conditions, list) else {}
        overlap_evidence: dict[str, Any] = {}
        recomputed_overlap_by_condition: dict[str, Any] = {}
        strategy_projection_evidence: dict[str, Any] = {}
        overlap_projection_receipt_bound = False
        overlap_task_probe_descriptor_bound = False
        overlap_refs_bound = (
            set(condition_rows) == set(OBJECTIVE_CONDITION_ORDER)
            and set(cycle_condition_rows) == set(OBJECTIVE_CONDITION_ORDER))
        if overlap_refs_bound:
            for condition in OBJECTIVE_CONDITION_ORDER:
                persisted = condition_rows[condition]
                summarized = cycle_condition_rows[condition]
                evidence = summarized.get("task_family_prompt_delivery_evidence")
                if (not isinstance(evidence, Mapping)
                        or persisted.get("inference_receipt_id") !=
                            summarized.get("inference_receipt_id")
                        or persisted.get("inference_receipt_digest") !=
                            summarized.get("inference_receipt_digest")):
                    overlap_refs_bound = False
                    break
                try:
                    receipt = receipt_verifier(persisted)
                except Exception as exc:
                    raise ValueError(
                        "retrospective_audit_transfer_projection_receipt_invalid") from exc
                request = receipt.get("request") if isinstance(receipt, Mapping) else None
                upstream = (request.get("upstream_evidence")
                    if isinstance(request, Mapping) else None)
                projection = (upstream.get("task_family_history_prompt_projection")
                    if isinstance(upstream, Mapping) else None)
                if not isinstance(projection, Mapping):
                    raise ValueError(
                        "retrospective_audit_transfer_projection_missing_from_receipt")
                projection_semantic = dict(projection)
                projection_digest = projection_semantic.pop("projection_digest", None)
                if (not isinstance(projection_digest, str)
                        or projection_digest != "sha256:" + digest_payload(
                            projection_semantic)
                        or evidence.get("projection_digest") != projection_digest):
                    raise ValueError(
                        "retrospective_audit_transfer_projection_digest_mismatch")
                accumulated_strategy = projection.get(
                    "accumulated_candidate_integer_affine_strategy")
                evidence_schema = evidence.get("schema_version")
                if evidence_schema == (
                        "sentientos.objective_task_family_prompt_delivery_evidence:v5"):
                    if accumulated_strategy is None:
                        expected_strategy_status = (
                            "withheld_condition_candidate_absent"
                            if condition == "history_withheld" else
                            "no_candidate_in_projection")
                        prompt_binding_posture = projection.get(
                            "accumulated_candidate_prompt_binding_posture")
                        if (projection.get("schema_version") in {
                                "sentientos.task_family_history_prompt_projection:v28",
                                "sentientos.task_family_history_prompt_projection:v29",
                                "sentientos.task_family_history_prompt_projection:v30",
                                "sentientos.task_family_history_prompt_projection:v31",
                                "sentientos.task_family_history_prompt_projection:v32",
                                "sentientos.task_family_history_prompt_projection:v33",
                                "sentientos.task_family_history_prompt_projection:v34",
                                "sentientos.task_family_history_prompt_projection:v35"}
                                and prompt_binding_posture !=
                                    "no_accumulated_candidate_in_projection"):
                            raise ValueError(
                                "retrospective_audit_accumulated_strategy_prompt_binding_invalid")
                        expected_strategy_values = {
                            "accumulated_strategy_schema_version": None,
                            "accumulated_strategy_digest": None,
                            "accumulated_strategy_anchor_run_digests": None,
                            "accumulated_strategy_supporting_run_count": None,
                            "accumulated_strategy_distinct_input_count": None,
                            "accumulated_strategy_prompt_binding_posture":
                                prompt_binding_posture,
                        }
                    else:
                        if not isinstance(accumulated_strategy, Mapping):
                            raise ValueError(
                                "retrospective_audit_accumulated_strategy_invalid")
                        strategy_semantic = dict(accumulated_strategy)
                        strategy_digest = strategy_semantic.pop(
                            "strategy_digest", None)
                        anchors = accumulated_strategy.get(
                            "independent_input_anchor_run_digests")
                        compact_strategy_projection = projection.get(
                            "schema_version") in {
                                "sentientos.task_family_history_prompt_projection:v32",
                                "sentientos.task_family_history_prompt_projection:v33",
                                "sentientos.task_family_history_prompt_projection:v34",
                                "sentientos.task_family_history_prompt_projection:v35"}
                        expected_strategy_schema_version = (
                            "sentientos.accumulated_integer_affine_strategy:v9"
                            if compact_strategy_projection else
                            "sentientos.accumulated_integer_affine_strategy:v8")
                        if (condition == "history_withheld"
                                or projection.get("schema_version") not in {
                                    "sentientos.task_family_history_prompt_projection:v26",
                                    "sentientos.task_family_history_prompt_projection:v27",
                                    "sentientos.task_family_history_prompt_projection:v28",
                                    "sentientos.task_family_history_prompt_projection:v29",
                                    "sentientos.task_family_history_prompt_projection:v30",
                                    "sentientos.task_family_history_prompt_projection:v31",
                                    "sentientos.task_family_history_prompt_projection:v32",
                                    "sentientos.task_family_history_prompt_projection:v33",
                                    "sentientos.task_family_history_prompt_projection:v34",
                                    "sentientos.task_family_history_prompt_projection:v35"}
                                or accumulated_strategy.get("schema_version") !=
                                    expected_strategy_schema_version
                                or not isinstance(strategy_digest, str)
                                or strategy_digest != "sha256:" + digest_payload(
                                    strategy_semantic)
                                or accumulated_strategy.get("task_family_id")
                                    != task_family_id
                                or accumulated_strategy.get("historical_only") is not True
                                or accumulated_strategy.get("current_truth") is not False
                                or accumulated_strategy.get("authority") is not False
                                or accumulated_strategy.get(
                                    "learning_established") is not False
                                or accumulated_strategy.get(
                                    "performance_transfer_established") is not False
                                or not isinstance(anchors, list)
                                or len(anchors) != 2
                                or any(not isinstance(value, str)
                                    or re.fullmatch(r"sha256:[0-9a-f]{64}",
                                        value) is None for value in anchors)
                                or len(set(anchors)) != 2
                                or accumulated_strategy.get(
                                    "independent_input_anchor_run_digests_digest")
                                    != "sha256:" + digest_payload(anchors)
                                or accumulated_strategy.get(
                                    "independent_input_anchor_run_count") != 2
                                or type(accumulated_strategy.get(
                                    "supporting_run_count")) is not int
                                or accumulated_strategy["supporting_run_count"] < 2
                                or type(accumulated_strategy.get(
                                    "supporting_distinct_input_count")) is not int
                                or accumulated_strategy[
                                    "supporting_distinct_input_count"] < 3):
                            raise ValueError(
                                "retrospective_audit_accumulated_strategy_invalid")
                        prompt_binding_posture = projection.get(
                            "accumulated_candidate_prompt_binding_posture")
                        if projection.get("schema_version") in {
                                "sentientos.task_family_history_prompt_projection:v28",
                                "sentientos.task_family_history_prompt_projection:v29",
                                "sentientos.task_family_history_prompt_projection:v30",
                                "sentientos.task_family_history_prompt_projection:v31",
                                "sentientos.task_family_history_prompt_projection:v32",
                                "sentientos.task_family_history_prompt_projection:v33",
                                "sentientos.task_family_history_prompt_projection:v34",
                                "sentientos.task_family_history_prompt_projection:v35"}:
                            expected_prompt_posture = (
                                "canonical_compact_accumulated_strategy_substring_in_exact_prompt:v1"
                                if compact_strategy_projection
                                else "canonical_accumulated_strategy_substring_in_exact_prompt:v1")
                            if prompt_binding_posture != expected_prompt_posture:
                                raise ValueError(
                                    "retrospective_audit_accumulated_strategy_prompt_binding_invalid")
                            strategy_version = (
                                "v9" if compact_strategy_projection else "v8")
                            expected_strategy_status = (
                                f"{strategy_version}_candidate_substring_bound_to_owner_prompt")
                        else:
                            strategy_version = (
                                "v9" if compact_strategy_projection else "v8")
                            expected_strategy_status = (
                                f"{strategy_version}_candidate_projection_prompt_inclusion_unmeasured")
                        expected_strategy_values = {
                            "accumulated_strategy_schema_version":
                                accumulated_strategy.get("schema_version"),
                            "accumulated_strategy_digest": strategy_digest,
                            "accumulated_strategy_anchor_run_digests": anchors,
                            "accumulated_strategy_supporting_run_count":
                                accumulated_strategy.get("supporting_run_count"),
                            "accumulated_strategy_distinct_input_count":
                                accumulated_strategy.get(
                                    "supporting_distinct_input_count"),
                            "accumulated_strategy_prompt_binding_posture":
                                prompt_binding_posture,
                        }
                    if (evidence.get("accumulated_strategy_delivery_status")
                                != expected_strategy_status
                            or any(evidence.get(key) != value
                                for key, value in expected_strategy_values.items())):
                        raise ValueError(
                            "retrospective_audit_accumulated_strategy_delivery_mismatch")
                    strategy_projection_evidence[condition] = {
                        "status": expected_strategy_status,
                        **expected_strategy_values,
                        "projection_digest_bound_to_verified_receipt": True,
                    }
                else:
                    strategy_projection_evidence[condition] = {
                        "status": "legacy_strategy_delivery_unmeasured",
                        "schema_version": evidence_schema,
                        "projection_digest_bound_to_verified_receipt": True,
                    }
                projection_schema = projection.get("schema_version")
                if projection_schema in {
                        "sentientos.task_family_history_prompt_projection:v24",
                        "sentientos.task_family_history_prompt_projection:v25",
                        "sentientos.task_family_history_prompt_projection:v26",
                        "sentientos.task_family_history_prompt_projection:v27",
                        "sentientos.task_family_history_prompt_projection:v28",
                        "sentientos.task_family_history_prompt_projection:v29",
                        "sentientos.task_family_history_prompt_projection:v30",
                        "sentientos.task_family_history_prompt_projection:v31",
                        "sentientos.task_family_history_prompt_projection:v32",
                        "sentientos.task_family_history_prompt_projection:v33",
                        "sentientos.task_family_history_prompt_projection:v34",
                        "sentientos.task_family_history_prompt_projection:v35"}:
                    descriptor_probe_inputs = transfer_descriptor.get("probe_inputs")
                    if (not isinstance(descriptor_probe_inputs, list)
                            or not descriptor_probe_inputs
                            or any(type(value) is not int
                                for value in descriptor_probe_inputs)
                            or len(set(descriptor_probe_inputs))
                                != len(descriptor_probe_inputs)
                            or projection.get("task_probe_input_count")
                                != len(descriptor_probe_inputs)
                            or projection.get("task_probe_input_digest")
                                != "sha256:" + digest_payload({
                                    "probe_inputs": descriptor_probe_inputs})):
                        raise ValueError(
                            "retrospective_audit_transfer_task_probe_binding_mismatch")
                    overlap_task_probe_descriptor_bound = True
                    projection_records = projection.get("records")
                    retrieved_ids = persisted.get("retrieved_record_ids")
                    retrieved_digests = persisted.get("retrieved_record_digests")
                    if (not isinstance(projection_records, list)
                            or any(not isinstance(row, Mapping)
                                for row in projection_records)
                            or not isinstance(retrieved_ids, list)
                            or not isinstance(retrieved_digests, list)
                            or [row.get("record_id") for row in projection_records]
                                != retrieved_ids
                            or [row.get("record_digest") for row in projection_records]
                                != retrieved_digests):
                        raise ValueError(
                            "retrospective_audit_transfer_history_refs_mismatch")
                    history_packets = []
                    for record_ref in projection_records:
                        selected_record = history_store.get(
                            record_ref["record_id"])
                        if selected_record.record_digest != record_ref.get(
                                "record_digest"):
                            raise ValueError(
                                "retrospective_audit_transfer_history_record_digest_mismatch")
                        history_packets.append(_history_context_packet(
                            dict(selected_record.__dict__),
                            include_source_evidence_context=False,
                            compact_for_input_budget=True,
                            omit_historical_embodiment_details=True,
                            task_family_id=task_family_id,
                            target_model_identity=cycle["active_model_identity"]))
                    recomputed_overlap = _task_family_history_probe_overlap(
                        history_packets,
                        task_probe_inputs=descriptor_probe_inputs)
                    if any(projection.get(key) != value
                            for key, value in recomputed_overlap.items()):
                        raise ValueError(
                            "retrospective_audit_transfer_overlap_recompute_mismatch")
                    recomputed_overlap_by_condition[condition] = {
                        "posture": ("exact_probe_reuse_detected"
                            if recomputed_overlap[
                                "historical_probe_overlap_input_count"] > 0 else
                            "no_exact_probe_reuse_detected"
                            if recomputed_overlap[
                                "historical_probe_overlap_measurement_complete"] else
                            "exact_probe_reuse_measurement_incomplete"),
                        "measure": recomputed_overlap,
                        "recomputed_from_verified_selected_records": True,
                    }
                    projection_fields = {
                        "task_probe_input_count": projection.get(
                            "task_probe_input_count"),
                        "task_probe_input_digest": projection.get(
                            "task_probe_input_digest"),
                        "historical_probe_overlap_input_digest": projection.get(
                            "historical_probe_overlap_input_digest"),
                        "historical_probe_overlap_example_count": projection.get(
                            "historical_probe_overlap_example_count"),
                        "historical_probe_overlap_input_count": projection.get(
                            "historical_probe_overlap_input_count"),
                        "historical_probe_overlap_posture": projection.get(
                            "historical_probe_overlap_posture"),
                        "historical_probe_overlap_measurement_complete": projection.get(
                            "historical_probe_overlap_measurement_complete"),
                    }
                    if any(evidence.get(key) != value
                            for key, value in projection_fields.items()):
                        raise ValueError(
                            "retrospective_audit_transfer_projection_summary_mismatch")
                    if (type(projection.get(
                            "historical_probe_overlap_input_count")) is int
                            and projection["historical_probe_overlap_input_count"] > 0):
                        receipt_posture = "exact_probe_reuse_detected"
                    elif projection.get(
                            "historical_probe_overlap_measurement_complete") is True:
                        receipt_posture = "no_exact_probe_reuse_detected"
                    else:
                        receipt_posture = "exact_probe_reuse_measurement_incomplete"
                else:
                    receipt_posture = "exact_probe_reuse_legacy_unmeasured"
                    recomputed_overlap_by_condition[condition] = {
                        "posture": receipt_posture,
                        "measure": None,
                        "recomputed_from_verified_selected_records": False,
                    }
                    if evidence.get("exact_probe_reuse_posture") != receipt_posture:
                        raise ValueError(
                            "retrospective_audit_legacy_projection_posture_mismatch")
                if evidence.get("exact_probe_reuse_posture") != receipt_posture:
                    raise ValueError(
                        "retrospective_audit_transfer_projection_posture_mismatch")
                overlap_evidence[condition] = dict(evidence)
            overlap_projection_receipt_bound = overlap_refs_bound
        if overlap_refs_bound:
            scored_conditions = ("history_present", "history_restored")
            postures = [overlap_evidence[condition].get(
                "exact_probe_reuse_posture") for condition in scored_conditions]
            if any(posture == "exact_probe_reuse_detected" for posture in postures):
                overlap_posture = "exact_probe_reuse_detected"
            elif all(posture == "no_exact_probe_reuse_detected"
                    for posture in postures):
                overlap_posture = "no_exact_probe_reuse_detected"
            elif any(posture == "exact_probe_reuse_legacy_unmeasured"
                    for posture in postures):
                overlap_posture = "exact_probe_reuse_legacy_unmeasured"
            else:
                overlap_posture = "exact_probe_reuse_measurement_incomplete"
            overlap_posture_bound = (
                transfer.get("exact_probe_reuse_posture") == overlap_posture)
        else:
            overlap_posture = "exact_probe_reuse_evidence_unbound"
            overlap_posture_bound = False
        if not overlap_refs_bound:
            overlap_posture = "exact_probe_reuse_evidence_unbound"
        transfer_run_audit = {
            "status": "owner_verified",
            "run_id": transfer_run_id,
            "run_digest": transfer_run_digest,
            "run_file_sha256": hashlib.sha256(transfer_run_raw).hexdigest(),
            "owner_run_reload_verified": True,
            "condition_summary_binding_verified": True,
            "condition_score_summaries": transfer_score_summaries,
            "accumulated_strategy_projection_audit": {
                "status": (
                    "condition_strategy_projection_evidence_bound"
                    if len(strategy_projection_evidence) ==
                        len(OBJECTIVE_CONDITION_ORDER)
                    and all(item.get("status") !=
                        "legacy_strategy_delivery_unmeasured"
                        for item in strategy_projection_evidence.values())
                    else "legacy_strategy_delivery_unmeasured"
                    if strategy_projection_evidence else "not_assessed"),
                "condition_evidence": strategy_projection_evidence or None,
                "projection_digests_bound_to_verified_receipts": (
                    len(strategy_projection_evidence) ==
                        len(OBJECTIVE_CONDITION_ORDER)),
                "model_attention_established": False,
                "learning_established": False,
                "authority": False,
            },
            "exact_probe_reuse_audit": {
                "posture": overlap_posture,
                "cycle_summary_condition_evidence": overlap_evidence
                    if overlap_refs_bound else None,
                "recomputed_condition_evidence": recomputed_overlap_by_condition
                    if overlap_refs_bound else None,
                "condition_receipt_refs_bound_to_owner_verified_run":
                    overlap_refs_bound,
                "projection_digest_bound_to_verified_receipt":
                    overlap_projection_receipt_bound,
                "task_probe_inputs_bound_to_verified_run_descriptor":
                    overlap_task_probe_descriptor_bound,
                "overlap_recomputed_from_verified_selected_records":
                    overlap_projection_receipt_bound
                    and overlap_task_probe_descriptor_bound,
                "aggregate_posture_matches_condition_evidence":
                    overlap_posture_bound,
                "prompt_delivery_independently_reconstructed": False,
                "learning_established": False,
                "authority": False,
            },
            "paired_probe_outcome_summary": _paired_probe_outcome_summary(
                transfer_score_summaries, OBJECTIVE_CONDITION_ORDER),
            "inference_performed": False,
        }
        if isinstance(cycle_transfer_conditions, list):
            cycle_delivery_rows = [row for row in cycle_transfer_conditions
                if isinstance(row, Mapping)]
            delivery_versions = {row.get(
                "task_family_prompt_delivery_evidence", {}).get(
                    "schema_version")
                for row in cycle_delivery_rows
                if isinstance(row.get("task_family_prompt_delivery_evidence"),
                    Mapping)}
            if delivery_versions == {
                    "sentientos.objective_task_family_prompt_delivery_evidence:v5"}:
                transfer_projection_delivery_audit = (
                    _audit_transfer_projection_delivery_v5(
                        task_family_id=task_family_id,
                        transfer_descriptor=transfer_descriptor,
                        transfer_conditions=transfer_conditions,
                        cycle_transfer_conditions=cycle_transfer_conditions,
                        receipt_verifier=receipt_verifier,
                        history_store=history_store))
            elif not overlap_refs_bound:
                transfer_projection_delivery_audit = (
                    _audit_legacy_transfer_projection_delivery(
                    task_family_id=task_family_id,
                    transfer_descriptor=transfer_descriptor,
                    transfer_conditions=transfer_conditions,
                    cycle_transfer_conditions=cycle_transfer_conditions,
                    receipt_verifier=receipt_verifier,
                    history_store=history_store))

    intervention_value = cycle.get("history_intervention")
    intervention_audit = (_audit_history_intervention_receipts(
        cycle=cycle, intervention=intervention_value,
        receipt_root=receipt_root)
        if isinstance(intervention_value, Mapping) else
        {"status": "not_present", "receipt_and_prompt_output_bindings_verified": False,
            "inference_performed": False, "learning_claim_made": False})
    later_decision_audit = _audit_later_companion_decision(
        cycle=cycle, receipt_root=receipt_root,
        intervention_audit=intervention_audit)

    semantic = {
        "schema_version": "sentientos.rootless_acquisition_history_retrospective_audit:v17",
        "cycle_id": cycle.get("run_id"),
        "cycle_status": cycle.get("status"),
        "cycle_result_file_sha256": hashlib.sha256(cycle_raw).hexdigest(),
        "acquisition_history_record": {
            "record_id": record.record_id,
            "record_digest": record.record_digest,
            "record_file_sha256": hashlib.sha256(record_raw).hexdigest(),
            "owner_digest_and_posture_verified": True,
        },
        "acquisition_run": {
            "source_run_count": len(acquisition_runs),
            "source_run_ids": sorted(source_runs),
            "source_runs": acquisition_runs,
            "owner_run_reload_verified": all(row[
                "owner_run_reload_verified"] for row in acquisition_runs),
            "history_record_score_binding_verified": source_score_binding_verified,
            "history_record_score_binding_method": score_binding_method,
        },
        "invocation_receipt_verification": {
            "schema_version": "sentientos.offline_rootless_receipt_verification:v1",
            "receipt_payloads_verified_through_owner_session_verifier": True,
            "receipt_observation_request_and_condition_bindings_verified": True,
            "cycle_preregistration_run_runtime_and_model_bindings_verified": True,
            "live_session_instance_reconstructed": False,
            "independent_backend_attestation": False,
            "inference_performed": False,
        },
        "history_projection_audit": audit,
        "history_intervention_audit": intervention_audit,
        "later_companion_decision_audit": later_decision_audit,
        "transfer": {
            "status": transfer.get("status"),
            "withheld_baseline_correct_count": transfer.get(
                "acquisition_task_outcome", {}).get(
                    "history_withheld_baseline_correct_count"),
            "required_baseline_correct_count": transfer.get(
                "acquisition_task_outcome", {}).get(
                    "baseline_competence_threshold"),
            "transfer_result_present": transfer.get("run_id") is not None,
            "run_audit": transfer_run_audit,
            "projection_delivery_audit": transfer_projection_delivery_audit,
        },
        "prompt_delivery_assessed": False,
        "model_attention_established": False,
        "learning_claim_made": False,
        "performance_improvement_established": False,
        "authority": False,
    }
    artifact = {**semantic, "audit_digest": digest_payload(semantic)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n"
    if output_path.exists():
        if output_path.read_text(encoding="utf-8") != serialized:
            raise ValueError("retrospective_audit_immutable_artifact_mismatch")
    else:
        output_path.write_text(serialized, encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    artifact = create_audit(cycle_root=args.cycle_root, output_path=args.output)
    print(json.dumps({"artifact": str(args.output),
        "audit_digest": artifact["audit_digest"],
        "owner_run_reload_verified": artifact["acquisition_run"][
            "owner_run_reload_verified"],
        "receipts_verified": artifact["invocation_receipt_verification"][
            "receipt_payloads_verified_through_owner_session_verifier"],
        "inference_performed": False,
        "learning_claim_made": False}, sort_keys=True))


if __name__ == "__main__":
    main()
