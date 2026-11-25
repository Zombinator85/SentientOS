"""Summarize the latest digest-verified rootless cognition audit per cycle.

This reads retrospective audit artifacts only. It does not reopen cycle stores,
invoke inference, or pool cycle scores into a learning claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.local_model_authority import digest_payload


_AUDIT_NAME = re.compile(
    r"retrospective_acquisition_history_audit_v(?P<version>[0-9]+)\.json")
_CURRENT_RETROSPECTIVE_AUDIT_VERSION = 17


def _read_latest_audits(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir():
        raise ValueError("persisted_experiment_root_unavailable")
    summaries: list[dict[str, Any]] = []
    for cycle_dir in sorted(root.glob("rootless_cognition_cycle_*")):
        if not cycle_dir.is_dir():
            continue
        candidates: list[tuple[int, Path]] = []
        for path in cycle_dir.glob("retrospective_acquisition_history_audit_v*.json"):
            match = _AUDIT_NAME.fullmatch(path.name)
            if match:
                candidates.append((int(match.group("version")), path))
        if not candidates:
            continue
        version, path = max(candidates, key=lambda item: item[0])
        try:
            audit = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("persisted_experiment_audit_unreadable") from exc
        if not isinstance(audit, dict):
            raise ValueError("persisted_experiment_audit_invalid")
        semantic = {key: value for key, value in audit.items()
            if key != "audit_digest"}
        expected_cycle_id = cycle_dir.name.replace("rootless_cognition_cycle_",
            "rootless-cognition-cycle-", 1)
        schema_version = audit.get("schema_version")
        if (schema_version != f"sentientos.rootless_acquisition_history_retrospective_audit:v{version}"
                or audit.get("audit_digest") != digest_payload(semantic)
                or audit.get("cycle_id") != expected_cycle_id
                or audit.get("learning_claim_made") is not False
                or audit.get("authority") is not False):
            raise ValueError("persisted_experiment_audit_binding_invalid")
        acquisition = audit.get("acquisition_run")
        acquisition_scores = (acquisition.get("condition_score_summaries")
            if isinstance(acquisition, dict) else None)
        acquisition_source_runs = None
        acquisition_source_run_count = None
        if version in {16, 17}:
            source_runs = (acquisition.get("source_runs")
                if isinstance(acquisition, dict) else None)
            source_run_ids = (acquisition.get("source_run_ids")
                if isinstance(acquisition, dict) else None)
            source_run_count = (acquisition.get("source_run_count")
                if isinstance(acquisition, dict) else None)
            if (not isinstance(source_runs, list) or not source_runs
                    or type(source_run_count) is not int
                    or source_run_count != len(source_runs)
                    or not isinstance(source_run_ids, list)
                    or any(not isinstance(run_id, str)
                        for run_id in source_run_ids)
                    or source_run_ids != sorted(set(source_run_ids))
                    or len(source_run_ids) != len(source_runs)):
                raise ValueError("persisted_experiment_acquisition_run_set_invalid")
            normalized_source_runs = []
            for source_run in source_runs:
                if (not isinstance(source_run, dict)
                        or not isinstance(source_run.get("run_id"), str)
                        or re.fullmatch(r"devexp-run-[0-9a-f]{24}",
                            source_run["run_id"]) is None
                        or not isinstance(source_run.get("condition_score_summaries"), dict)
                        or set(source_run.get("condition_score_summaries", {}))
                            != {"history_present", "history_withheld",
                                "history_restored"}
                        or type(source_run.get(
                            "history_record_score_binding_verified")) is not bool
                        or type(source_run.get("owner_run_reload_verified")) is not bool):
                    raise ValueError(
                        "persisted_experiment_acquisition_run_invalid")
                normalized_source_runs.append({
                    "run_id": source_run["run_id"],
                    "history_record_score_binding_verified": source_run[
                        "history_record_score_binding_verified"],
                    "owner_run_reload_verified": source_run[
                        "owner_run_reload_verified"],
                    "condition_score_summaries": source_run[
                        "condition_score_summaries"],
                })
            if sorted(row["run_id"] for row in normalized_source_runs) != source_run_ids:
                raise ValueError("persisted_experiment_acquisition_run_set_invalid")
            all_run_bindings_verified = all(row[
                "history_record_score_binding_verified"]
                for row in normalized_source_runs)
            all_run_reloads_verified = all(row["owner_run_reload_verified"]
                for row in normalized_source_runs)
            if (type(acquisition.get(
                    "history_record_score_binding_verified")) is not bool
                    or acquisition["history_record_score_binding_verified"]
                        is not all_run_bindings_verified
                    or type(acquisition.get("owner_run_reload_verified")) is not bool
                    or acquisition["owner_run_reload_verified"]
                        is not all_run_reloads_verified):
                raise ValueError(
                    "persisted_experiment_acquisition_run_rollup_invalid")
            acquisition_source_runs = normalized_source_runs
            acquisition_source_run_count = source_run_count
            if source_run_count == 1:
                acquisition_scores = normalized_source_runs[0][
                    "condition_score_summaries"]
        transfer = audit.get("transfer")
        transfer_run = transfer.get("run_audit") if isinstance(transfer, dict) else None
        transfer_scores = (transfer_run.get("condition_score_summaries")
            if isinstance(transfer_run, dict) else None)
        transfer_overlap = (transfer_run.get("exact_probe_reuse_audit")
            if isinstance(transfer_run, dict) else None)
        accumulated_strategy_audit = (transfer_run.get(
            "accumulated_strategy_projection_audit")
            if isinstance(transfer_run, dict) else None)
        paired_outcomes = (transfer_run.get("paired_probe_outcome_summary")
            if isinstance(transfer_run, dict) else None)
        projection_delivery = transfer.get("projection_delivery_audit") \
            if isinstance(transfer, dict) else None
        projection = audit.get("history_projection_audit")
        intervention = audit.get("history_intervention_audit")
        decision = audit.get("later_companion_decision_audit")
        summaries.append({
            "cycle_id": audit["cycle_id"],
            "audit_schema_version": version,
            "audit_schema_posture": (
                "current" if version == _CURRENT_RETROSPECTIVE_AUDIT_VERSION
                else "older_than_current" if version <
                    _CURRENT_RETROSPECTIVE_AUDIT_VERSION
                else "newer_than_summarizer"),
            "audit_digest_verified": True,
            "cycle_status": audit.get("cycle_status"),
            "task_family_id": (projection.get("task_family_id")
                if isinstance(projection, dict) else None),
            "history_projection_status": (projection.get("status")
                if isinstance(projection, dict) else None),
            "history_quarantined": (projection.get("history_quarantined")
                if isinstance(projection, dict) else None),
            "history_quarantine_reason_code": (
                projection.get("quarantine_reason_code")
                if isinstance(projection, dict) else None),
            "projectable_experience_count": (
                projection.get("projectable_experience_count")
                if isinstance(projection, dict) else None),
            "task_relevant_record_count": (
                projection.get("task_relevant_record_count")
                if isinstance(projection, dict) else None),
            "task_relevant_example_count": (
                projection.get("task_relevant_example_count")
                if isinstance(projection, dict) else None),
            "projection_prompt_delivery_status": (
                projection.get("prompt_delivery_status")
                if isinstance(projection, dict) else None),
            "acquisition_condition_scores": acquisition_scores,
            "acquisition_source_run_count": acquisition_source_run_count,
            "acquisition_condition_scores_by_source_run": acquisition_source_runs,
            "transfer_status": (transfer.get("status")
                if isinstance(transfer, dict) else None),
            "transfer_result_present": (transfer.get("transfer_result_present")
                if isinstance(transfer, dict) else None),
            "withheld_baseline_correct_count": (transfer.get(
                "withheld_baseline_correct_count")
                if isinstance(transfer, dict) else None),
            "required_baseline_correct_count": (transfer.get(
                "required_baseline_correct_count")
                if isinstance(transfer, dict) else None),
            "transfer_condition_scores": transfer_scores,
            "transfer_paired_probe_outcome_summary": paired_outcomes,
            "transfer_exact_probe_reuse_posture": (
                transfer_overlap.get("posture")
                if isinstance(transfer_overlap, dict) else None),
            "transfer_overlap_recomputed_from_verified_selected_records": (
                transfer_overlap.get(
                    "overlap_recomputed_from_verified_selected_records")
                if isinstance(transfer_overlap, dict) else None),
            "transfer_projection_delivery_status": (
                projection_delivery.get("status")
                if isinstance(projection_delivery, dict) else None),
            "transfer_projection_prompt_digest_bound": (
                projection_delivery.get("projection_prompt_digest_bound")
                if isinstance(projection_delivery, dict) else None),
            "transfer_selected_history_record_refs_reloaded": (
                projection_delivery.get("selected_history_record_refs_reloaded")
                if isinstance(projection_delivery, dict) else None),
            "transfer_exact_prompt_serialization_reconstructed": (
                projection_delivery.get("exact_prompt_serialization_reconstructed")
                if isinstance(projection_delivery, dict) else None),
            "history_present_restored_prompt_matches": (
                intervention.get("history_present_restored_prompt_matches")
                if isinstance(intervention, dict) else None),
            "history_present_withheld_prompt_differs": (
                intervention.get("history_present_withheld_prompt_differs")
                if isinstance(intervention, dict) else None),
            "history_present_restored_output_matches": (
                intervention.get("history_present_restored_output_matches")
                if isinstance(intervention, dict) else None),
            "history_present_withheld_output_differs": (
                intervention.get("history_present_withheld_output_differs")
                if isinstance(intervention, dict) else None),
            "prompt_delivery_assessed": audit.get("prompt_delivery_assessed"),
            "transfer_task_relevant_example_counts": ({condition: evidence.get(
                    "task_relevant_example_count")
                for condition, evidence in projection_delivery.get(
                    "condition_evidence", {}).items()
                if isinstance(evidence, dict)}
                if isinstance(projection_delivery, dict) else None),
            "transfer_accumulated_strategy_delivery_status": (
                accumulated_strategy_audit.get("status")
                if isinstance(accumulated_strategy_audit, dict) else None),
            "transfer_accumulated_strategy_condition_evidence": (
                accumulated_strategy_audit.get("condition_evidence")
                if isinstance(accumulated_strategy_audit, dict) else None),
            "history_changed_cognition": (decision.get("history_changed_cognition")
                if isinstance(decision, dict) else None),
            "model_attention_established": audit.get(
                "model_attention_established"),
            "intervention_status": (intervention.get("status")
                if isinstance(intervention, dict) else None),
            "learning_claim_made": False,
            "performance_improvement_established": False,
        })
    return summaries


def _read_incomplete_runs(roots: list[Path]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            raise ValueError("persisted_failure_root_unavailable")
        for cycle_dir in sorted(root.glob("rootless-cognition-cycle-*")):
            path = cycle_dir / "cycle-failure.json"
            if not path.is_file():
                continue
            try:
                failure = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError("persisted_failure_artifact_unreadable") from exc
            if (not isinstance(failure, dict)
                    or failure.get("status") != "incomplete"
                    or failure.get("run_id") != cycle_dir.name):
                raise ValueError("persisted_failure_artifact_binding_invalid")
            stage_journal = failure.get("stage_journal")
            checkpoints = (stage_journal.get("checkpoints")
                if isinstance(stage_journal, dict) else None)
            diagnostic = failure.get("failure_diagnostic")
            if (not isinstance(diagnostic, dict)
                    or diagnostic.get("schema_version") !=
                        "sentientos.rootless_python_failure_diagnostic:v1"):
                diagnostic = None
            elif set(diagnostic) != {
                    "schema_version", "failure_kind", "unresolved_identifier",
                    "module", "function", "line", "exception_message_included",
                    "source_line_included", "authority"}:
                diagnostic = None
            summaries.append({
                "cycle_id": failure["run_id"],
                "stage": failure.get("stage"),
                "failure_type": failure.get("failure_type"),
                "failure_code": failure.get("failure_code"),
                "failure_cause_code": failure.get("failure_cause_code"),
                "python_failure_diagnostic": diagnostic,
                "persisted_receipt_count": (len(failure["inference_receipts"])
                    if isinstance(failure.get("inference_receipts"), list) else None),
                "persisted_developmental_record_count": (
                    len(failure["governed_developmental_records"])
                    if isinstance(failure.get("governed_developmental_records"), list)
                    else None),
                "reported_stage_journal_status": (
                    stage_journal.get("integrity_status")
                    if isinstance(stage_journal, dict) else None),
                "last_entered_stage": (stage_journal.get("last_entered_stage")
                    if isinstance(stage_journal, dict) else None),
                "all_reported_checkpoint_digests_verified": (
                    all(isinstance(row, dict)
                        and row.get("digest_verified") is True
                        for row in checkpoints)
                    if isinstance(checkpoints, list) else None),
                "artifact_posture": "incomplete_failure_record_not_independently_authenticated",
                "learning_claim_made": False,
            })
    return sorted(summaries, key=lambda row: row["cycle_id"])


def _read_history_transfer_audit(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        raw = path.read_bytes()
        audit = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("history_transfer_audit_unreadable") from exc
    if (not isinstance(audit, dict)
            or audit.get("schema_version") !=
                "sentientos.history_transfer_precondition_audit:v5"
            or audit.get("measurement_scope") !=
                "persisted_artifact_readiness_summary"
            or audit.get("inference_performed") is not False
            or audit.get("learning_claim_made") is not False
            or audit.get("skipped_probes_are_negative_results") is not False):
        raise ValueError("history_transfer_audit_posture_invalid")
    rows = audit.get("runs")
    if (not isinstance(rows, list)
            or type(audit.get("artifact_count")) is not int
            or audit["artifact_count"] != len(rows)
            or type(audit.get("valid_artifact_count")) is not int
            or type(audit.get("artifact_error_count")) is not int
            or audit["valid_artifact_count"] + audit["artifact_error_count"]
                != audit["artifact_count"]):
        raise ValueError("history_transfer_audit_counts_invalid")
    valid_rows = [row for row in rows
        if isinstance(row, dict) and "artifact_error" not in row]
    if len(valid_rows) != audit["valid_artifact_count"]:
        raise ValueError("history_transfer_audit_valid_count_mismatch")
    for row in valid_rows:
        for field in ("pattern_match_fact_ids",
                "source_binding_valid_fact_ids", "verified_source_fact_ids",
                "source_provenance_failure_codes"):
            values = row.get(field)
            if (not isinstance(values, list)
                    or any(not isinstance(value, str) for value in values)):
                raise ValueError("history_transfer_audit_row_evidence_invalid")
        if not isinstance(row.get("record_snapshot_binding_status"), str):
            raise ValueError("history_transfer_audit_row_binding_invalid")
    recomputed = {
        "source_binding_valid_pattern_fact_count": sum(
            len(row.get("source_binding_valid_fact_ids", []))
            for row in valid_rows),
        "verified_source_pattern_fact_count": sum(
            len(row.get("verified_source_fact_ids", []))
            for row in valid_rows
            if row.get("record_snapshot_binding_status") ==
                "exact_record_snapshot_match"),
        "retrospective_verified_source_fact_count": sum(
            len(row.get("verified_source_fact_ids", []))
            for row in valid_rows
            if row.get("record_snapshot_binding_status") !=
                "exact_record_snapshot_match"),
        "runtime_snapshot_bound_pattern_match_count": sum(
            bool(row.get("pattern_match_fact_ids")) for row in valid_rows
            if row.get("record_snapshot_binding_status") ==
                "exact_record_snapshot_match"),
        "observer_key_custody_unverified_record_count": sum(
            "observer_key_custody_provenance_unverified" in row.get(
                "source_provenance_failure_codes") for row in valid_rows),
    }
    if any(type(audit.get(key)) is not int or audit[key] != value
            for key, value in recomputed.items()):
        raise ValueError("history_transfer_audit_rollup_mismatch")
    return {
        "source_path": str(path.resolve()),
        "report_sha256": hashlib.sha256(raw).hexdigest(),
        "schema_version": audit["schema_version"],
        "artifact_count": audit["artifact_count"],
        "valid_artifact_count": audit["valid_artifact_count"],
        "artifact_error_count": audit["artifact_error_count"],
        **recomputed,
        "source_provenance_failure_code_counts": audit.get(
            "source_provenance_failure_code_counts"),
        "transfer_status_counts": audit.get("transfer_status_counts"),
        "objective_transfer_status_counts": audit.get(
            "objective_transfer_status_counts"),
        "inference_performed": False,
        "learning_claim_made": False,
        "internal_rollups_recomputed": True,
    }


def main() -> None:
    default_root = Path(__file__).resolve().parents[1] / "artifacts" / "experiments"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root,
        help="directory containing rootless_cognition_cycle_* audit folders")
    parser.add_argument("--failure-root", type=Path, action="append", default=[],
        help="optional runtime directory containing rootless-cognition-cycle-* failure records")
    parser.add_argument("--history-transfer-audit", type=Path,
        help="optional v5 action-decision readiness audit to include separately")
    args = parser.parse_args()
    summaries = _read_latest_audits(args.root.resolve())
    incomplete_runs = _read_incomplete_runs(
        [path.resolve() for path in args.failure_root])
    history_transfer_audit = _read_history_transfer_audit(
        args.history_transfer_audit.resolve()
        if args.history_transfer_audit is not None else None)
    print(json.dumps({
        "schema_version": "sentientos.persisted_cognition_audit_summary:v7",
        "current_retrospective_audit_schema_version": (
            _CURRENT_RETROSPECTIVE_AUDIT_VERSION),
        "source_root": str(args.root.resolve()),
        "cycle_count": len(summaries),
        "incomplete_run_count": len(incomplete_runs),
        "pooled_learning_claim": False,
        "history_transfer_gate_audit": history_transfer_audit,
        "cycles": summaries,
        "incomplete_runs": incomplete_runs,
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
