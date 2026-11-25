#!/usr/bin/env python3
"""Recompute digest-bound score summaries in a partial rootless transfer audit."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from sentientos.local_model_authority import digest_payload

MAX_AUDIT_BYTES = 4 * 1024 * 1024
MAX_SOURCE_BYTES = 8 * 1024 * 1024
CONDITION_ORDER = ("history_present", "history_withheld", "history_restored")


class AuditVerificationError(ValueError):
    """The audit or its persisted source evidence does not verify."""


def _read_object(path: Path, *, max_bytes: int, code: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise AuditVerificationError(code)
    try:
        if path.stat().st_size > max_bytes:
            raise AuditVerificationError(code)
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditVerificationError(code) from exc
    if not isinstance(value, dict):
        raise AuditVerificationError(code)
    return value


def _source_path(workspace_root: Path, relative: object) -> Path:
    if (not isinstance(relative, str) or not relative
            or "\\" in relative):
        raise AuditVerificationError("partial_transfer_source_path_invalid")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or relative != pure.as_posix():
        raise AuditVerificationError("partial_transfer_source_path_invalid")
    candidate = workspace_root.joinpath(*pure.parts)
    current = workspace_root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise AuditVerificationError("partial_transfer_source_path_symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(workspace_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise AuditVerificationError("partial_transfer_source_path_outside_workspace") from exc
    return resolved


def _score_summary(run: Mapping[str, Any], *, expected_run_id: str,
        source_run: Mapping[str, Any]) -> dict[str, Any]:
    if run.get("run_id") != expected_run_id:
        raise AuditVerificationError("partial_transfer_run_identity_mismatch")
    body = {key: value for key, value in run.items()
        if key not in {"run_id", "run_digest"}}
    expected_digest = digest_payload(body)
    if (run.get("run_digest") != "sha256:" + expected_digest
            or run.get("schema_version") !=
                "sentientos.developmental_history_intervention_run:v3"):
        raise AuditVerificationError("partial_transfer_run_digest_invalid")
    protocol = run.get("protocol")
    scores = run.get("objective_scores")
    conditions = run.get("conditions")
    if (not isinstance(protocol, Mapping)
            or not isinstance(scores, list) or len(scores) != len(CONDITION_ORDER)
            or not isinstance(conditions, list)
            or len(conditions) != len(CONDITION_ORDER)
            or [row.get("condition_id") for row in scores
                if isinstance(row, Mapping)] != list(CONDITION_ORDER)
            or [row.get("condition_id") for row in conditions
                if isinstance(row, Mapping)] != list(CONDITION_ORDER)):
        raise AuditVerificationError("partial_transfer_run_condition_shape_invalid")
    descriptor = protocol.get("objective_task_descriptor")
    if (not isinstance(descriptor, Mapping)
            or descriptor.get("task_digest") != source_run.get("task_digest")
            or descriptor.get("task_family_id") != source_run.get("task_family_id")):
        raise AuditVerificationError("partial_transfer_run_task_binding_invalid")
    if protocol.get("active_model_identity_digest") is None:
        raise AuditVerificationError("partial_transfer_model_identity_missing")
    model_identity_digest = protocol.get("active_model_identity_digest")
    if (not isinstance(model_identity_digest, str)
            or re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}",
                model_identity_digest) is None):
        raise AuditVerificationError("partial_transfer_model_identity_invalid")
    rows: list[dict[str, Any]] = []
    output_digests: set[str] = set()
    probe_inputs: list[int] | None = None
    for row, condition in zip(scores, conditions):
        if not isinstance(row, Mapping) or not isinstance(condition, Mapping):
            raise AuditVerificationError("partial_transfer_score_row_invalid")
        score = row.get("score")
        if (not isinstance(score, Mapping)
                or score.get("schema_version") not in {
                    "sentientos.objective_task_score:v5",
                    "sentientos.objective_task_score:v6"}
                or score.get("task_digest") != descriptor.get("task_digest")
                or score.get("plan_digest") is None):
            raise AuditVerificationError("partial_transfer_score_binding_invalid")
        score_body = {key: value for key, value in score.items()
            if key != "score_digest"}
        if score.get("score_digest") != "sha256:" + digest_payload(score_body):
            raise AuditVerificationError("partial_transfer_score_digest_invalid")
        output_digest = row.get("invocation_output_digest")
        if (not isinstance(output_digest, str)
                or score.get("output_digest") != output_digest
                or condition.get("output_digest") != output_digest):
            raise AuditVerificationError("partial_transfer_output_binding_invalid")
        results = score.get("probe_results")
        if not isinstance(results, list) or not results:
            raise AuditVerificationError("partial_transfer_probe_results_invalid")
        inputs = [item.get("probe_input") for item in results
            if isinstance(item, Mapping)]
        if (len(inputs) != len(results)
                or any(type(value) is not int for value in inputs)
                or len(set(inputs)) != len(inputs)):
            raise AuditVerificationError("partial_transfer_probe_inputs_invalid")
        if probe_inputs is None:
            probe_inputs = inputs
        elif inputs != probe_inputs:
            raise AuditVerificationError("partial_transfer_condition_probe_set_changed")
        correct_count = sum(item.get("correct") is True for item in results
            if isinstance(item, Mapping))
        abstained_count = sum((item.get("abstained") is True
            or item.get("observed_answer") is None)
            for item in results if isinstance(item, Mapping))
        answered_count = len(results) - abstained_count
        if (score.get("probe_count") != len(results)
                or score.get("correct_count") != correct_count
                or score.get("abstained_count") != abstained_count
                or score.get("answered_count") != answered_count):
            raise AuditVerificationError("partial_transfer_score_counts_invalid")
        output_digests.add(output_digest)
        rows.append({
            "condition_id": row["condition_id"],
            "score_schema": score["schema_version"],
            "probe_count": len(results),
            "correct_count": correct_count,
            "answered_count": answered_count,
            "abstained_count": abstained_count,
            "status": score.get("status"),
            "output_digest": output_digest,
            "score_digest": score["score_digest"],
            "output_digest_binding_verified": True,
        })
    if len(output_digests) == 1:
        output_posture = "identical_condition_output_digests"
    else:
        output_posture = "condition_output_digests_differ"
    return {"run_id": run["run_id"], "run_digest": run["run_digest"],
        "task_digest": descriptor["task_digest"],
        "task_family_id": descriptor["task_family_id"],
        "target_model_identity_digest": model_identity_digest,
        "probe_count": len(probe_inputs or []),
        "_probe_inputs": list(probe_inputs or []),
        "probe_set_digest": "sha256:" + digest_payload(probe_inputs or []),
        "condition_output_digest_count": len(output_digests),
        "condition_output_posture": output_posture,
        "score_rows": rows}


def _verify_prompt_context_delivery(*, audit: Mapping[str, Any],
        runs: Mapping[str, Mapping[str, Any]], workspace_root: Path,
        cycle_id: str) -> int:
    """Recompute the digest-only prompt audit from the retained receipts."""
    delivery = audit.get("prompt_context_delivery")
    expected_conditions = ("history_present", "history_withheld",
        "history_restored")
    if (not isinstance(delivery, Mapping)
            or delivery.get("raw_prompts_or_outputs_included") is not False
            or delivery.get("model_attention_or_strategy_use_established") is not False
            or delivery.get("exact_governed_request_prompt_digest_binding_verified") is not True
            or delivery.get("history_present_and_restored_share_accumulated_strategy_digest") is not True
            or delivery.get("history_withheld_has_no_selected_records_or_accumulated_strategy") is not True):
        raise AuditVerificationError("partial_transfer_prompt_audit_claims_invalid")
    conditions = delivery.get("conditions")
    if (not isinstance(conditions, list) or len(conditions) != len(expected_conditions)
            or tuple(item.get("condition_id") for item in conditions
                if isinstance(item, Mapping)) != expected_conditions):
        raise AuditVerificationError("partial_transfer_prompt_conditions_invalid")
    receipt_root = _source_path(workspace_root,
        PurePosixPath("sentientos-data", "rootless-experimental",
            "developmental-cognition-cycles", cycle_id,
            "inference-custody", "receipts").as_posix())
    by_condition: dict[str, dict[str, Any]] = {}
    for condition, audit_row in zip(expected_conditions, conditions):
        if not isinstance(audit_row, Mapping):
            raise AuditVerificationError("partial_transfer_prompt_condition_invalid")
        matches = [score_row for score_row in
            runs["transfer"].get("objective_scores", [])
            if isinstance(score_row, Mapping)
                and score_row.get("condition_id") == condition]
        if len(matches) != 1:
            raise AuditVerificationError("partial_transfer_prompt_score_binding_invalid")
        score_row = matches[0]
        receipt_id = audit_row.get("receipt_id")
        if (not isinstance(receipt_id, str)
                or re.fullmatch(r"lmrec-[0-9a-f]{24}", receipt_id) is None
                or score_row.get("inference_receipt_id") != receipt_id):
            raise AuditVerificationError("partial_transfer_prompt_receipt_id_mismatch")
        receipt_path = _source_path(workspace_root,
            PurePosixPath(receipt_root.relative_to(workspace_root).as_posix(),
                receipt_id + ".json").as_posix())
        receipt_raw = receipt_path.read_bytes()
        if len(receipt_raw) > MAX_SOURCE_BYTES:
            raise AuditVerificationError("partial_transfer_prompt_receipt_unbounded")
        try:
            receipt = json.loads(receipt_raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise AuditVerificationError(
                "partial_transfer_prompt_receipt_invalid") from exc
        if not isinstance(receipt, Mapping):
            raise AuditVerificationError("partial_transfer_prompt_receipt_invalid")
        raw_digest = hashlib.sha256(receipt_raw).hexdigest()
        request = receipt.get("request")
        linkage = request.get("linkage") if isinstance(request, Mapping) else None
        session_link = (linkage.get("rootless_experimental_session")
            if isinstance(linkage, Mapping) else None)
        upstream = request.get("upstream_evidence") if isinstance(request, Mapping) else None
        projection = (upstream.get("task_family_history_prompt_projection")
            if isinstance(upstream, Mapping) else None)
        if (raw_digest != audit_row.get("receipt_source_file_sha256")
                or receipt.get("receipt_id") != receipt_id
                or score_row.get("inference_receipt_digest") != receipt.get("receipt_digest")
                or not isinstance(request, Mapping)
                or request.get("prompt_digest") != audit_row.get("request_prompt_digest")
                or not isinstance(linkage, Mapping)
                or not isinstance(session_link, Mapping)
                or session_link.get("run_id") != cycle_id
                or linkage.get("condition_id") != condition
                or not isinstance(upstream, Mapping)
                or not isinstance(projection, Mapping)):
            raise AuditVerificationError("partial_transfer_prompt_receipt_binding_invalid")
        semantic_projection = {key: value for key, value in projection.items()
            if key != "projection_digest"}
        if (projection.get("projection_digest") != "sha256:" +
                digest_payload(semantic_projection)
                or projection.get("projection_digest") != audit_row.get("projection_digest")
                or projection.get("schema_version") != audit_row.get("projection_schema")
                or projection.get("governed_request_prompt_digest") != request.get("prompt_digest")
                or projection.get("condition_id") != condition
                or receipt.get("output_digest") != score_row.get("invocation_output_digest")
                or upstream.get("record_ids") != [row.get("record_id")
                    for row in projection.get("records", [])
                    if isinstance(row, Mapping)]
                or len(projection.get("records", [])) != audit_row.get("selected_record_count")
                or projection.get("selected_record_count") != audit_row.get("selected_record_count")
                or projection.get("task_relevant_record_count") != audit_row.get("task_relevant_record_count")
                or projection.get("candidate_integer_affine_strategy_count") != audit_row.get("candidate_strategy_count")):
            raise AuditVerificationError("partial_transfer_prompt_projection_binding_invalid")
        strategy = projection.get("accumulated_candidate_integer_affine_strategy")
        strategy_digest = (strategy.get("strategy_digest")
            if isinstance(strategy, Mapping) else None)
        if (audit_row.get("accumulated_strategy_present") != (strategy_digest is not None)
                or audit_row.get("accumulated_strategy_digest") != strategy_digest
                or audit_row.get("prompt_binding_posture") != projection.get("prompt_binding_posture")
                or audit_row.get("verification") != {
                    "projection_digest_verified": True,
                    "raw_prompt_not_stored": True,
                    "receipt_output_digest_bound": True,
                    "request_prompt_digest_bound": True,
                    "retrieval_ids_match_condition": True}):
            raise AuditVerificationError("partial_transfer_prompt_projection_claim_invalid")
        by_condition[condition] = {"record_ids": list(upstream["record_ids"]),
            "strategy_digest": strategy_digest}
    if (by_condition["history_present"] != by_condition["history_restored"]
            or by_condition["history_withheld"] != {
                "record_ids": [], "strategy_digest": None}):
        raise AuditVerificationError("partial_transfer_prompt_condition_contrast_invalid")
    acquired = audit.get("acquisition_history_record")
    if not isinstance(acquired, Mapping):
        raise AuditVerificationError("partial_transfer_acquisition_record_ref_invalid")
    record_id = acquired.get("record_id")
    if (not isinstance(record_id, str)
            or re.fullmatch(r"devrec-[0-9a-f]{24}", record_id) is None):
        raise AuditVerificationError("partial_transfer_acquisition_record_ref_invalid")
    record_path = _source_path(workspace_root,
        PurePosixPath("sentientos-data", "rootless-experimental",
            "developmental-cognition-cycles", cycle_id,
            "resident-cognition", "history", "records",
            record_id + ".json").as_posix())
    record_raw = record_path.read_bytes()
    if (len(record_raw) > MAX_SOURCE_BYTES
            or hashlib.sha256(record_raw).hexdigest() !=
                acquired.get("source_file_sha256")):
        raise AuditVerificationError("partial_transfer_acquisition_record_hash_mismatch")
    record = json.loads(record_raw.decode("utf-8"))
    if (not isinstance(record, Mapping)
            or record.get("record_id") != record_id
            or record.get("record_digest") != acquired.get("record_digest")
            or record_id not in by_condition["history_present"]["record_ids"]
            or record_id not in by_condition["history_restored"]["record_ids"]
            or record_id in by_condition["history_withheld"]["record_ids"]):
        raise AuditVerificationError("partial_transfer_acquisition_record_projection_mismatch")
    return len(conditions)


def verify_audit(*, audit_path: Path, workspace_root: Path) -> dict[str, Any]:
    audit_path = audit_path.resolve(strict=True)
    workspace_root = workspace_root.resolve(strict=True)
    audit = _read_object(audit_path, max_bytes=MAX_AUDIT_BYTES,
        code="partial_transfer_audit_invalid")
    if audit.get("schema_version") != "sentientos.rootless_partial_transfer_score_audit:v2":
        raise AuditVerificationError("partial_transfer_audit_schema_unsupported")
    semantic = {key: value for key, value in audit.items() if key != "audit_digest"}
    if audit.get("audit_digest") != "sha256:" + digest_payload(semantic):
        raise AuditVerificationError("partial_transfer_audit_digest_invalid")
    cycle_id = audit.get("cycle_id")
    if (not isinstance(cycle_id, str)
            or re.fullmatch(r"rootless-cognition-cycle-[0-9a-f]{20}",
                cycle_id) is None):
        raise AuditVerificationError("partial_transfer_cycle_identity_invalid")
    source_runs = audit.get("source_runs")
    if not isinstance(source_runs, Mapping) or set(source_runs) != {
            "acquisition", "transfer"}:
        raise AuditVerificationError("partial_transfer_source_runs_invalid")
    recomputed: dict[str, Any] = {}
    source_runs_loaded: dict[str, Mapping[str, Any]] = {}
    source_hashes_match = True
    for stage in ("acquisition", "transfer"):
        ref = source_runs[stage]
        if not isinstance(ref, Mapping):
            raise AuditVerificationError("partial_transfer_source_run_invalid")
        path = _source_path(workspace_root, ref.get("source_path"))
        raw = path.read_bytes()
        if len(raw) > MAX_SOURCE_BYTES:
            raise AuditVerificationError("partial_transfer_source_run_unbounded")
        source_hash_matches = hashlib.sha256(raw).hexdigest() == ref.get(
            "source_file_sha256")
        if not source_hash_matches:
            raise AuditVerificationError("partial_transfer_source_hash_mismatch")
        source_hashes_match = source_hashes_match and source_hash_matches
        run = json.loads(raw.decode("utf-8"))
        if not isinstance(run, dict):
            raise AuditVerificationError("partial_transfer_source_run_invalid")
        source_runs_loaded[stage] = run
        summary = _score_summary(run, expected_run_id=ref.get("run_id"),
            source_run=ref)
        if (summary["run_digest"] != ref.get("run_digest")
                or summary["task_digest"] != ref.get("task_digest")
                or summary["task_family_id"] != ref.get("task_family_id")
                or summary["probe_count"] != ref.get("probe_count")
                or summary["probe_set_digest"] != ref.get("probe_set_digest")):
            raise AuditVerificationError("partial_transfer_source_summary_mismatch")
        expected_rows = ref.get("score_rows")
        if not isinstance(expected_rows, list) or len(expected_rows) != len(
                summary["score_rows"]):
            raise AuditVerificationError("partial_transfer_score_rows_missing")
        for expected, actual in zip(expected_rows, summary["score_rows"]):
            aliases = {
                "condition_id": "condition_id",
                "score_schema": "score_schema",
                "probe_count": "probe_count",
                "correct_count": "correct_count",
                "answered_count": "answered_count",
                "abstained_count": "abstained_count",
                "status": "status",
                "score_digest": "score_digest",
            }
            if (not isinstance(expected, Mapping) or any(
                    expected.get(field) != actual.get(alias)
                    for field, alias in aliases.items())
                    or expected.get("condition_output_digest") != actual.get("output_digest")
                    or expected.get("score_output_digest") != actual.get("output_digest")
                    or expected.get("score_digest_verified") is not True
                    or expected.get("output_digest_binding_verified") is not True):
                raise AuditVerificationError("partial_transfer_score_row_mismatch")
        summary["source_file_sha256"] = hashlib.sha256(raw).hexdigest()
        summary["source_hash_matches_audit"] = source_hash_matches
        recomputed[stage] = summary
    if (recomputed["acquisition"]["task_family_id"] !=
            recomputed["transfer"]["task_family_id"]
            or recomputed["acquisition"]["task_digest"] ==
                recomputed["transfer"]["task_digest"]
            or recomputed["acquisition"]["probe_set_digest"] ==
                recomputed["transfer"]["probe_set_digest"]):
        raise AuditVerificationError("partial_transfer_task_comparison_invalid")
    acquisition_inputs = set(recomputed["acquisition"]["_probe_inputs"])
    transfer_inputs = set(recomputed["transfer"]["_probe_inputs"])
    task_comparison = audit.get("task_comparison")
    if (not isinstance(task_comparison, Mapping)
            or task_comparison.get("acquisition_probe_set_digest") !=
                recomputed["acquisition"]["probe_set_digest"]
            or task_comparison.get("transfer_probe_set_digest") !=
                recomputed["transfer"]["probe_set_digest"]
            or task_comparison.get("same_task_family") is not True
            or task_comparison.get("different_task_commitments") is not True
            or task_comparison.get("probe_sets_disjoint") is not True
            or not acquisition_inputs.isdisjoint(transfer_inputs)
            or recomputed["acquisition"]["target_model_identity_digest"] !=
                recomputed["transfer"]["target_model_identity_digest"]):
        raise AuditVerificationError("partial_transfer_task_comparison_binding_invalid")
    claims = audit.get("claims")
    required_claims = {
        "authority": False,
        "behavioral_scores_persisted": True,
        "inference_performed": True,
        "learning_established": False,
        "model_attention_established": False,
        "prompt_integration_verified": True,
        "raw_prompts_answers_or_model_outputs_included": False,
        "transfer_established": False,
    }
    if (not isinstance(claims, Mapping)
            or any(claims.get(key) is not value
                for key, value in required_claims.items())):
        raise AuditVerificationError("partial_transfer_claims_invalid")
    failure_ref = audit.get("failure_artifact")
    if not isinstance(failure_ref, Mapping):
        raise AuditVerificationError("partial_transfer_failure_ref_invalid")
    failure_path = _source_path(workspace_root, failure_ref.get("source_path"))
    failure_raw = failure_path.read_bytes()
    if len(failure_raw) > MAX_SOURCE_BYTES:
        raise AuditVerificationError("partial_transfer_failure_unbounded")
    failure_hash_matches = hashlib.sha256(failure_raw).hexdigest() == failure_ref.get(
        "source_file_sha256")
    if not failure_hash_matches:
        raise AuditVerificationError("partial_transfer_failure_hash_mismatch")
    failure = json.loads(failure_raw.decode("utf-8"))
    if (not isinstance(failure, Mapping)
            or failure.get("run_id") != cycle_id
            or failure.get("status") != "incomplete"
            or failure.get("failure_code") != failure_ref.get("failure_code")
            or failure.get("stage") != failure_ref.get("stage")):
        raise AuditVerificationError("partial_transfer_failure_binding_invalid")
    observed = audit.get("observed_result")
    if not isinstance(observed, Mapping):
        raise AuditVerificationError("partial_transfer_observed_result_invalid")
    acq_rows, transfer_rows = (recomputed["acquisition"]["score_rows"],
        recomputed["transfer"]["score_rows"])
    if (observed.get("acquisition_all_conditions_correct") != all(
            row["correct_count"] == row["probe_count"]
                and row["abstained_count"] == 0 for row in acq_rows)
            or observed.get("transfer_all_conditions_abstained") != all(
                row["abstained_count"] == row["probe_count"] for row in transfer_rows)):
        raise AuditVerificationError("partial_transfer_observed_result_mismatch")
    prompt_condition_count = _verify_prompt_context_delivery(audit=audit,
        runs=source_runs_loaded, workspace_root=workspace_root,
        cycle_id=cycle_id)
    for stage in ("acquisition", "transfer"):
        recomputed[stage].pop("_probe_inputs", None)
    return {"status": "verified", "audit_digest": audit["audit_digest"],
        "cycle_id": cycle_id,
        "source_hashes_match": source_hashes_match and failure_hash_matches,
        "failure_code": failure_ref["failure_code"],
        "failure_stage": failure_ref["stage"],
        "acquisition": recomputed["acquisition"],
        "transfer": recomputed["transfer"],
        "prompt_delivery_conditions_recomputed": prompt_condition_count,
        "inference_performed": True, "transfer_established": False,
        "learning_established": False, "authority": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True,
        help="root containing the audit's relative persisted source paths")
    args = parser.parse_args()
    try:
        result = verify_audit(audit_path=args.audit,
            workspace_root=args.workspace_root)
    except (AuditVerificationError, OSError, ValueError, TypeError,
            KeyError, UnicodeError, json.JSONDecodeError) as exc:
        code = (str(exc) if isinstance(exc, AuditVerificationError)
            else "partial_transfer_audit_verification_failed")
        raise SystemExit(code) from exc
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
