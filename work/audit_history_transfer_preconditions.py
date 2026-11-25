"""Summarize history-transfer readiness separately from completed cognition outcomes.

This is a read-only artifact audit. It does not load a model, change experiment
state, or reinterpret skipped probes as negative transfer results. A bridge
HMAC receipt proves transport authentication for a configured key; without
persisted evidence of external key custody it does not establish an independent
observer source.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sentientos.embodied_consequence import (  # noqa: E402
    EmbodiedConsequenceError,
    verify_consequence_attribution,
)
from sentientos.world_state_board import (  # noqa: E402
    record_digest as world_state_record_digest,
)
from sentientos.local_model_authority import digest_payload  # noqa: E402


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _source_binding_valid(fact: dict[str, Any]) -> bool:
    source = _mapping(fact.get("source"))
    subject = _mapping(fact.get("subject"))
    payload = _mapping(fact.get("payload"))
    if (source.get("kind") != "embodiment"
            or source.get("finding") != "ok"
            or source.get("source_id") != payload.get("attribution_id")
            or source.get("schema_version") != payload.get("schema_version")
            or subject.get("subject_id") != payload.get("expectation_id")
            or subject.get("subject_kind") != "embodied_consequence_attribution"
            or fact.get("stage") != "observation"
            or fact.get("disposition") != payload.get("classification")
            or fact.get("effect_claimed") is not False
            or fact.get("effect_proven") is not False):
        return False
    producer_record = {
        "source_kind": source.get("kind"),
        "source_id": source.get("source_id"),
        "schema_version": source.get("schema_version"),
        "subject_id": subject.get("subject_id"),
        "subject_kind": subject.get("subject_kind"),
        "stage": fact.get("stage"),
        "disposition": fact.get("disposition"),
        "effect_claimed": fact.get("effect_claimed"),
        "effect_proven": fact.get("effect_proven"),
        "payload": payload,
    }
    try:
        return (isinstance(source.get("digest"), str)
            and world_state_record_digest(producer_record) == source.get("digest"))
    except (TypeError, ValueError, RecursionError):
        return False


def _selected_record_pattern(record_path: Path, *,
        expected_record_digest: str | None = None) -> dict[str, Any]:
    """Scan patterns and run the source attribution's historical validator."""
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"record_read_status": "unavailable",
                "record_snapshot_binding_status": "record_unavailable",
                "expected_record_digest": expected_record_digest,
                "actual_record_digest": None,
                "pattern_match_fact_ids": [],
                "source_binding_valid_fact_ids": [],
                "verified_source_fact_ids": [],
                "provenance_failure_codes": []}
    record_value = _mapping(record)
    try:
        actual_record_digest = digest_payload(record_value)
    except (TypeError, ValueError, OverflowError, RecursionError):
        actual_record_digest = None
    if expected_record_digest is None:
        snapshot_binding_status = "not_bound_by_cycle_artifact"
    elif actual_record_digest == expected_record_digest:
        snapshot_binding_status = "exact_record_snapshot_match"
    else:
        snapshot_binding_status = "record_snapshot_digest_mismatch"
    candidate = _mapping(record_value.get("candidate"))
    facts = candidate.get("selected_facts")
    if not isinstance(facts, list):
        return {"record_read_status": "selected_facts_unavailable",
                "record_snapshot_binding_status": snapshot_binding_status,
                "expected_record_digest": expected_record_digest,
                "actual_record_digest": actual_record_digest,
                "pattern_match_fact_ids": [], "source_binding_valid_fact_ids": [],
                "verified_source_fact_ids": [],
                "provenance_failure_codes": []}

    pattern_ids: list[str] = []
    source_binding_ids: list[str] = []
    verified_source_ids: list[str] = []
    provenance_failure_codes: set[str] = set()
    for fact_value in facts:
        fact = _mapping(fact_value)
        payload = _mapping(fact.get("payload"))
        source = _mapping(fact.get("source"))
        schema = payload.get("schema_version") or source.get("schema_version")
        if schema not in {
                "sentientos.embodied_consequence_attribution:v1",
                "sentientos.embodied_consequence_attribution:v2"}:
            continue
        commanded = _mapping(payload.get("commanded_value"))
        predicted = _mapping(payload.get("predicted_value"))
        observed = _mapping(payload.get("independently_observed_value"))
        if not (commanded.get("pose") == "reach"
                and commanded.get("task_goal") == "reach_marked_target"
                and predicted.get("pose") == "reach"
                and observed.get("pose") == "idle"
                and observed.get("task_goal_met") is False):
            continue
        fact_id = fact.get("fact_id")
        if not isinstance(fact_id, str) or not fact_id:
            continue
        pattern_ids.append(fact_id)
        source_binding_valid = _source_binding_valid(fact)
        if source_binding_valid:
            source_binding_ids.append(fact_id)
        try:
            verify_consequence_attribution(payload)
            source_valid = True
        except (EmbodiedConsequenceError, KeyError, TypeError, ValueError,
                OverflowError):
            source_valid = False
        if not source_binding_valid:
            provenance_failure_codes.add(
                "selected_history_fact_source_binding_invalid")
        elif schema != "sentientos.embodied_consequence_attribution:v2":
            provenance_failure_codes.add(
                "observation_attribution_schema_legacy_or_unsupported")
        elif (_mapping(payload.get("observation_authentication_receipt")).get(
                "observer_fixture_posture") == "same_process_synthetic_fixture"):
            provenance_failure_codes.add(
                "same_process_synthetic_observer_not_independent_history")
        elif (source_valid
                and _mapping(payload.get(
                    "observation_authentication_receipt")).get(
                        "schema_version") ==
                    "sentientos.authenticated_observer_ingress_receipt:v1"):
            provenance_failure_codes.add(
                "observer_key_custody_provenance_unverified")
        elif (payload.get("observation_independence_posture")
                != "authenticated_source_distinct_from_renderer_at_ingress"):
            provenance_failure_codes.add(
                "observation_independence_posture_unverified")
        elif (not isinstance(payload.get("observation_authentication_receipt"), Mapping)
                or not source_valid):
            provenance_failure_codes.add(
                "observation_authentication_receipt_invalid")
        else:
            verified_source_ids.append(fact_id)
    return {
        "record_read_status": "read_structural_and_source_validation",
        "record_snapshot_binding_status": snapshot_binding_status,
        "expected_record_digest": expected_record_digest,
        "actual_record_digest": actual_record_digest,
        "pattern_match_fact_ids": sorted(set(pattern_ids)),
        "source_binding_valid_fact_ids": sorted(set(source_binding_ids)),
        "verified_source_fact_ids": sorted(set(verified_source_ids)),
        "provenance_failure_codes": sorted(provenance_failure_codes),
    }


def audit(paths: list[Path]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted(paths):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            rows.append({"path": str(path), "artifact_error": type(exc).__name__})
            continue
        if not isinstance(result, dict):
            rows.append({"path": str(path), "artifact_error": "root_not_object"})
            continue

        intervention = _mapping(result.get("history_transfer_intervention"))
        readiness = _mapping(intervention.get("history_evidence_precondition"))
        objective_transfer = _mapping(result.get("objective_task_family_transfer"))
        history_seed = _mapping(result.get("prior_developmental_history_seed"))
        record_id = readiness.get("record_id")
        record_audit = (_selected_record_pattern(
            path.parent / "resident-cognition" / "history" / "records" /
            f"{record_id}.json",
            expected_record_digest=(readiness.get("retained_record_digest")
                if isinstance(readiness.get("retained_record_digest"), str)
                else None)) if isinstance(record_id, str) and record_id
            else {"record_read_status": "record_id_unavailable",
                  "record_snapshot_binding_status": "record_id_unavailable",
                  "expected_record_digest": None,
                  "actual_record_digest": None,
                  "pattern_match_fact_ids": [],
                  "source_binding_valid_fact_ids": [],
                  "verified_source_fact_ids": [],
                  "provenance_failure_codes": []})
        rows.append({
            "path": str(path),
            "run_id": result.get("run_id"),
            "cycle_id": path.parent.name,
            "result_status": result.get("status"),
            "transfer_status": intervention.get("status"),
            "transfer_classification": intervention.get("classification"),
            "readiness_eligible": readiness.get("eligible"),
            "readiness_reason": readiness.get("reason_code"),
            "readiness_record_id": record_id,
            "pattern_match_fact_ids": readiness.get("pattern_match_fact_ids", []),
            "eligible_evidence_fact_ids": readiness.get("evidence_fact_ids", []),
            "source_provenance_failure_codes": record_audit[
                "provenance_failure_codes"],
            **record_audit,
            "objective_transfer_status": objective_transfer.get("status"),
            "history_seed_status": history_seed.get("status"),
            "model_attention_verified": history_seed.get("model_attention_verified"),
            "action_executed": intervention.get("action_executed"),
            "performance_improvement_established": intervention.get(
                "performance_improvement_established"),
        })
        row = rows[-1]
        row["structural_readiness_classification"] = (
            "pattern_matches_with_verified_source_attribution"
            if row["pattern_match_fact_ids"]
            and row.get("record_snapshot_binding_status") ==
                "exact_record_snapshot_match"
            and row["verified_source_fact_ids"]
            else "pattern_matches_unverified_observation"
            if (row["pattern_match_fact_ids"]
                and row.get("record_snapshot_binding_status") ==
                    "exact_record_snapshot_match")
            else "final_record_pattern_not_bound_to_runtime_precondition"
            if row["pattern_match_fact_ids"]
            else "pattern_not_found_or_record_unavailable")

    valid = [row for row in rows if "artifact_error" not in row]
    return {
        "schema_version": "sentientos.history_transfer_precondition_audit:v5",
        "measurement_scope": "persisted_artifact_readiness_summary",
        "inference_performed": False,
        "learning_claim_made": False,
        "skipped_probes_are_negative_results": False,
        "artifact_count": len(rows),
        "valid_artifact_count": len(valid),
        "artifact_error_count": len(rows) - len(valid),
        "source_binding_valid_pattern_fact_count": sum(
            len(row.get("source_binding_valid_fact_ids", [])) for row in valid),
        "verified_source_pattern_fact_count": sum(
            len(row.get("verified_source_fact_ids", [])) for row in valid
            if row.get("record_snapshot_binding_status") ==
                "exact_record_snapshot_match"),
        "retrospective_verified_source_fact_count": sum(
            len(row.get("verified_source_fact_ids", [])) for row in valid
            if row.get("record_snapshot_binding_status") !=
                "exact_record_snapshot_match"),
        "runtime_snapshot_bound_pattern_match_count": sum(
            bool(row.get("pattern_match_fact_ids")) for row in valid
            if row.get("record_snapshot_binding_status") ==
                "exact_record_snapshot_match"),
        "observer_key_custody_unverified_record_count": sum(
            "observer_key_custody_provenance_unverified" in row.get(
                "source_provenance_failure_codes", []) for row in valid),
        "readiness_reason_counts": dict(sorted(Counter(
            str(row.get("readiness_reason", "missing")) for row in valid
        ).items())),
        "structural_readiness_classification_counts": dict(sorted(Counter(
            str(row.get("structural_readiness_classification", "missing"))
            for row in valid
        ).items())),
        "record_snapshot_binding_status_counts": dict(sorted(Counter(
            str(row.get("record_snapshot_binding_status", "missing"))
            for row in valid
        ).items())),
        "source_provenance_failure_code_counts": dict(sorted(Counter(
            code for row in valid for code in
            row.get("source_provenance_failure_codes", [])
        ).items())),
        "transfer_status_counts": dict(sorted(Counter(
            str(row.get("transfer_status", "missing")) for row in valid
        ).items())),
        "objective_transfer_status_counts": dict(sorted(Counter(
            str(row.get("objective_transfer_status", "missing")) for row in valid
        ).items())),
        "runs": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path,
                        help="cycle-result.json files or directories to search")
    args = parser.parse_args()
    files: list[Path] = []
    for path in args.paths:
        if path.is_dir():
            files.extend(path.rglob("cycle-result.json"))
        elif path.is_file():
            files.append(path)
    report = audit(files)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["artifact_error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
