#!/usr/bin/env python3
"""Read-only diagnostics for persisted SentientOS developmental-cycle failures.

The report contains identifiers and digests only. It never prints prompts,
model output, or mutates cycle artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

OWNER_FEEDBACK_KIND = "owner_verified_companion_qualification_feedback:v1"
WRITEBACK_SUFFIX = ":resident-developmental-writeback"


def _digest(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_mapping(path: Path) -> Mapping[str, Any] | None:
    try:
        value = _read_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _receipt_validation(receipt: Mapping[str, Any] | None) -> tuple[str, list[str]]:
    if receipt is None:
        return "missing", []
    repository_root = Path(__file__).resolve().parents[1]
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    try:
        from sentientos.governed_local_model_invocation import validate_receipt
        valid, reasons = validate_receipt(receipt)
    except (ImportError, OSError, TypeError, ValueError):
        return "validator_unavailable", []
    safe_reasons = [
        reason for reason in reasons
        if isinstance(reason, str)
        and reason.replace("_", "").isalnum()
        and len(reason) <= 96
    ]
    return ("verified" if valid and not safe_reasons else "invalid"), safe_reasons


def _companion_response_findings(root: Path) -> list[dict[str, Any]]:
    state = root / "resident-cognition" / "state"
    runs = state / "developmental_experiments" / "runs"
    receipts = root / "inference-custody" / "receipts"
    findings: list[dict[str, Any]] = []
    if not runs.is_dir():
        return findings
    for run_path in sorted(runs.glob("*.json")):
        run = _load_mapping(run_path)
        if run is None:
            continue
        semantic_run = {
            key: value for key, value in run.items()
            if key not in {"run_id", "run_digest"}
        }
        run_digest_valid = (
            run.get("run_digest") == "sha256:" + _digest(semantic_run)
        )
        decisions = run.get("companion_intervention_decisions")
        if not isinstance(decisions, list):
            continue
        for index, decision in enumerate(decisions):
            if not isinstance(decision, Mapping):
                continue
            receipt_id = decision.get("inference_receipt_id")
            receipt_path = receipts / (str(receipt_id) + ".json")
            receipt = _load_mapping(receipt_path)
            receipt_integrity, receipt_validation_reasons = (
                _receipt_validation(receipt))
            output_text = receipt.get("output_text") if receipt else None
            output_text_valid = (
                isinstance(output_text, str)
                and receipt.get("output_truncated") is False
                and receipt.get("output_digest") == _digest({"output": output_text})
                and receipt.get("output_size_bytes")
                    == len(output_text.encode("utf-8"))
            )
            response_digest: str | None = None
            response_is_string = False
            if output_text_valid:
                try:
                    output_value = json.loads(output_text)
                except json.JSONDecodeError:
                    output_value = None
                response = (
                    output_value.get("response")
                    if isinstance(output_value, Mapping) else None
                )
                response_is_string = isinstance(response, str)
                if response_is_string:
                    response_digest = _digest({"text": response})
            decision_digest = decision.get("response_digest")
            validation_status = decision.get("decision_validation_status")
            normalization = decision.get("disposition_normalization")
            rejected_marker_matches = (
                validation_status == "rejected_invalid_output"
                and decision_digest
                    == _digest({"text": "INVALID_EXPERIMENTAL_RESPONSE"})
            )
            if response_digest is not None and response_digest == decision_digest:
                response_assessment = "receipt_response_digest_verified"
            elif rejected_marker_matches:
                response_assessment = "rejected_output_marker_digest_verified"
            elif validation_status == "validated" and isinstance(normalization, str):
                response_assessment = "governed_normalized_response_not_reconstructible"
            else:
                response_assessment = "unexplained_response_digest_mismatch"
            receipt_id_matches = (
                receipt is not None and receipt.get("receipt_id") == receipt_id
            )
            receipt_digest_matches_decision = (
                receipt is not None
                and decision.get("inference_receipt_digest")
                    == receipt.get("receipt_digest")
            )
            output_digest_matches_receipt = (
                receipt is not None
                and decision.get("output_digest") == receipt.get("output_digest")
            )
            findings.append({
                "run_id": run.get("run_id"),
                "run_file": run_path.name,
                "run_digest_valid": run_digest_valid,
                "decision_index": index,
                "receipt_id": receipt_id,
                "receipt_present": receipt is not None,
                "receipt_semantic_integrity": receipt_integrity,
                "receipt_validation_reasons": receipt_validation_reasons,
                "receipt_id_matches_decision": receipt_id_matches,
                "receipt_digest_matches_decision": receipt_digest_matches_decision,
                "output_digest_matches_receipt": output_digest_matches_receipt,
                "receipt_output_integrity": (
                    "verified" if output_text_valid else "missing_or_invalid"
                ),
                "receipt_response_is_string": response_is_string,
                "decision_response_digest": decision_digest,
                "receipt_response_digest": response_digest,
                "decision_validation_status": validation_status,
                "disposition_normalization": normalization,
                "response_digest_assessment": response_assessment,
                "response_digest_matches_receipt": (
                    response_digest == decision_digest
                    if response_digest is not None else False
                ),
                "rejected_marker_digest_matches": rejected_marker_matches,
            })
    return findings


def _feedback_recovery_findings(root: Path) -> list[dict[str, Any]]:
    state_dir = root / "resident-cognition" / "state"
    composition = _load_mapping(state_dir / "composition_state.json")
    records_dir = root / "resident-cognition" / "history" / "records"
    if composition is None or not records_dir.is_dir():
        return []
    completed = composition.get("completed_ticks")
    if not isinstance(completed, list):
        return []
    by_tick = {
        row.get("tick_id"): row
        for row in completed
        if isinstance(row, Mapping) and isinstance(row.get("tick_id"), str)
    }
    findings: list[dict[str, Any]] = []
    for record_path in sorted(records_dir.glob("*.json")):
        record = _load_mapping(record_path)
        if record is None:
            continue
        candidate = record.get("candidate")
        provenance = (
            candidate.get("transformation_provenance")
            if isinstance(candidate, Mapping) else None
        )
        if (not isinstance(provenance, Mapping)
                or provenance.get("kind") != OWNER_FEEDBACK_KIND):
            continue
        correlation = record.get("correlation_id")
        if not isinstance(correlation, str) or not correlation.endswith(WRITEBACK_SUFFIX):
            continue
        tick_id = correlation[:-len(WRITEBACK_SUFFIX)]
        checkpoint = by_tick.get(tick_id)
        if checkpoint is None:
            classification = "no_completed_tick_checkpoint"
            snapshot_matches = False
            checkpoint_empty = False
            record_matches = False
        else:
            snapshot_matches = (
                checkpoint.get("snapshot_id")
                    == candidate.get("snapshot_id")
                and checkpoint.get("snapshot_digest")
                    == candidate.get("snapshot_digest")
            )
            checkpoint_empty = (
                checkpoint.get("record_id") is None
                and checkpoint.get("receipt_id") is None
            )
            record_matches = checkpoint.get("record_id") == record.get("record_id")
            if record_matches:
                classification = "checkpoint_record_id_matches"
            elif checkpoint_empty and snapshot_matches:
                classification = "empty_checkpoint_snapshot_matches_feedback"
            else:
                classification = "checkpoint_conflict_requires_review"
        findings.append({
            "record_id": record.get("record_id"),
            "operation_id": record.get("operation_id"),
            "tick_id": tick_id,
            "checkpoint_classification": classification,
            "checkpoint_empty": checkpoint_empty,
            "checkpoint_snapshot_matches_record": snapshot_matches,
            "checkpoint_record_matches": record_matches,
            "record_file_sha256": hashlib.sha256(
                record_path.read_bytes()
            ).hexdigest(),
        })
    return findings


def inspect_cycle(root: Path) -> dict[str, Any]:
    failure_path = root / "cycle-failure.json"
    failure = _load_mapping(failure_path)
    if failure is None:
        raise ValueError(f"cycle-failure.json is missing or invalid under {root}")
    source_provenance = failure.get("source_provenance_at_failure")
    if not isinstance(source_provenance, Mapping):
        source_provenance = {}
    return {
        "schema": "sentientos.developmental_cycle_recovery_diagnostic:v1",
        "cycle_root": str(root),
        "cycle_id": failure.get("run_id"),
        "status": failure.get("status"),
        "stage": failure.get("stage"),
        "failure_code": failure.get("failure_code"),
        "source_revision_at_failure": source_provenance.get("repository_revision"),
        "source_worktree_status_at_failure": source_provenance.get(
            "worktree_content_status"),
        "source_worktree_clean_at_failure": source_provenance.get("worktree_clean"),
        "failure_file_sha256": hashlib.sha256(
            failure_path.read_bytes()
        ).hexdigest(),
        "companion_response_checks": _companion_response_findings(root),
        "owner_feedback_checkpoint_checks": _feedback_recovery_findings(root),
        "claims": {
            "model_output_included": False,
            "inference_performed": False,
            "learning_established": False,
            "authority": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cycle_root", type=Path,
        help="directory containing cycle-failure.json and persisted cycle artifacts")
    args = parser.parse_args()
    root = args.cycle_root.expanduser().resolve()
    try:
        report = inspect_cycle(root)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True, indent=2))
    has_integrity_conflict = any(
        not item.get("run_digest_valid")
        or item.get("receipt_semantic_integrity") != "verified"
        or not item.get("receipt_id_matches_decision")
        or not item.get("receipt_digest_matches_decision")
        or not item.get("output_digest_matches_receipt")
        or item.get("receipt_output_integrity") != "verified"
        or item.get("response_digest_assessment") in {
            "governed_normalized_response_not_reconstructible",
            "unexplained_response_digest_mismatch",
        }
        for item in report["companion_response_checks"]
    ) or any(
        item.get("checkpoint_classification")
            == "checkpoint_conflict_requires_review"
        for item in report["owner_feedback_checkpoint_checks"]
    )
    return 3 if has_integrity_conflict else 0


if __name__ == "__main__":
    raise SystemExit(main())
