#!/usr/bin/env python3
"""CPU-only verifier for cross-cycle recall receipts, protocol, and score rows.

Raw prompts and model output are read only for verification. The report retains
digests and categorical comparisons; it never includes either raw payload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

EXPECTED_CONDITIONS = ("history_present", "history_withheld", "history_restored")
RECEIPT_SCHEMA_PREFIX = "sentientos.local_model_invocation_receipt:v"


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalized_file_digest(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    ).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def semantic_receipt_digest(receipt: dict[str, Any]) -> str:
    schema = receipt.get("schema_version")
    if not isinstance(schema, str) or not schema.startswith(RECEIPT_SCHEMA_PREFIX):
        raise ValueError("unsupported_receipt_schema")
    try:
        version = int(schema.removeprefix(RECEIPT_SCHEMA_PREFIX))
    except ValueError as exc:
        raise ValueError("unsupported_receipt_schema") from exc
    if version < 2 or version > 10:
        raise ValueError("unsupported_receipt_schema")

    legacy_keys = (
        "request", "status", "reason_codes", "output_digest",
        "output_size_bytes", "generation_config", "admission_decision_ref",
        "purpose", "output_truncated", "fallback_occurred", "effects",
    )
    keys = ["schema_version", *legacy_keys, "observed_at"]
    versioned_fields = (
        (3, "backend_completion"),
        (4, "cancellation_admission_decision_ref"),
        (5, "cancellation_resource_observation"),
        (6, "cancellation_admission_decision"),
        (7, "cancellation_admission_record"),
        (8, "admission_decision_record"),
        (10, "cancellation_preemption_ref"),
    )
    keys.extend(field for first_version, field in versioned_fields
        if version >= first_version)
    return canonical_digest({key: receipt.get(key) for key in keys})


def audit(cycle_dir: Path, protocol_path: Path) -> dict[str, Any]:
    result_path = cycle_dir / "cycle-result.json"
    result_bytes = result_path.read_bytes()
    result = json.loads(result_bytes)
    recall = result.get("cross_cycle_owner_feedback_recall")
    if not isinstance(recall, dict):
        raise ValueError("cross_cycle_owner_feedback_recall_missing")
    protocol = read_json(protocol_path)
    protocol_digest = normalized_file_digest(protocol_path)
    if recall.get("protocol_digest") != protocol_digest:
        raise ValueError("protocol_digest_mismatch")
    expected = protocol.get("expected_outcomes")
    if not isinstance(expected, dict):
        raise ValueError("protocol_expected_outcomes_missing")
    rows = recall.get("conditions")
    if (not isinstance(rows, list) or len(rows) != len(EXPECTED_CONDITIONS)
            or {r.get("condition_id") for r in rows if isinstance(r, dict)}
                != set(EXPECTED_CONDITIONS)):
        raise ValueError("condition_inventory_mismatch")

    feedback_id = recall.get("feedback_record_id")
    feedback_digest = recall.get("feedback_record_digest")
    audited: list[dict[str, Any]] = []
    for row in rows:
        condition = row["condition_id"]
        receipt_id = row.get("inference_receipt_id")
        if (not isinstance(receipt_id, str)
                or re.fullmatch(r"lmrec-[0-9a-f]{24}", receipt_id) is None):
            raise ValueError("inference_receipt_id_invalid")
        receipt_path = (
            cycle_dir / "inference-custody" / "receipts" / f"{receipt_id}.json"
        )
        receipt_bytes = receipt_path.read_bytes()
        receipt = json.loads(receipt_bytes)
        semantic_digest = semantic_receipt_digest(receipt)
        raw_output = receipt.get("output_text")
        parsed: Any = None
        try:
            parsed = json.loads(raw_output) if isinstance(raw_output, str) else None
        except (json.JSONDecodeError, TypeError):
            pass
        if not isinstance(parsed, dict):
            parsed = {}

        expected_row = expected.get(condition)
        if not isinstance(expected_row, dict):
            raise ValueError("protocol_condition_missing")
        should_retrieve = (
            expected_row.get("retrieved_record_ids") == "exact_feedback_record_id"
        )
        expected_ids = [feedback_id] if should_retrieve else []
        expected_digests = [feedback_digest] if should_retrieve else []
        output_digest = canonical_digest({"output": raw_output})
        response = parsed.get("response")
        response_digest = (
            canonical_digest({"text": response}) if isinstance(response, str) else None
        )
        observed = {
            "response_matches_protocol": response == expected_row.get("response"),
            "disposition_matches_protocol": (
                parsed.get("disposition") == expected_row.get("disposition")
            ),
            "history_citations_match_protocol": (
                parsed.get("history_record_ids") == expected_ids
            ),
            "evidence_ids_match_protocol": (
                parsed.get("evidence_ids") == expected_row.get("evidence_ids")
            ),
            "score_row_expected_response_matches_protocol": (
                row.get("expected_response") == expected_row.get("response")
            ),
            "score_row_expected_disposition_matches_protocol": (
                row.get("expected_disposition") == expected_row.get("disposition")
            ),
            "score_row_selected_ids_match_protocol": (
                row.get("selected_record_ids") == expected_ids
            ),
            "score_row_selected_digests_match_protocol": (
                row.get("selected_record_digests") == expected_digests
            ),
        }
        links = {
            "receipt_id_matches": receipt.get("receipt_id") == receipt_id,
            "receipt_id_matches_semantic_digest": (
                receipt_id == "lmrec-" + semantic_digest[:24]
            ),
            "receipt_semantic_digest_matches": (
                receipt.get("receipt_digest") == semantic_digest
            ),
            "receipt_completed": receipt.get("status") == "admitted_completed",
            "output_digest_matches_receipt": (
                output_digest == receipt.get("output_digest")
            ),
            "output_size_matches_receipt": (
                isinstance(raw_output, str)
                and len(raw_output.encode("utf-8")) == receipt.get("output_size_bytes")
            ),
            "output_digest_matches_score": (
                receipt.get("output_digest") == row.get("output_digest")
            ),
            "response_digest_matches_score": (
                response_digest == row.get("response_digest")
            ),
        }
        audited.append({
            "condition_id": condition,
            "inference_receipt_id": receipt_id,
            "receipt_schema_version": receipt.get("schema_version"),
            "receipt_digest": semantic_digest,
            "receipt_file_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "output_digest": receipt.get("output_digest"),
            "response_digest": response_digest,
            "structured_output_parse_valid": isinstance(parsed, dict) and bool(parsed),
            "links": links,
            "protocol_criteria": observed,
            "recorded_decision_validation_status": row.get(
                "decision_validation_status"
            ),
            "recorded_condition_criteria_met": row.get("condition_criteria_met"),
            "all_receipt_links_verified": all(links.values()),
            "all_protocol_criteria_met": all(observed.values()),
        })

    all_links = all(
        item["all_receipt_links_verified"] and item["structured_output_parse_valid"]
        for item in audited
    )
    return {
        "schema_version": "sentientos.cross_cycle_recall_receipt_score_audit:v1",
        "cycle_id": cycle_dir.name,
        "cycle_result_sha256": hashlib.sha256(result_bytes).hexdigest(),
        "protocol_sha256": protocol_digest,
        "protocol_binding_verified": recall.get("protocol_digest") == protocol_digest,
        "recall_schema_version": recall.get("schema_version"),
        "recall_status": recall.get("status"),
        "condition_count": len(audited),
        "conditions": audited,
        "all_receipt_links_verified": all_links,
        "all_protocol_criteria_met": all(
            item["all_protocol_criteria_met"] for item in audited
        ),
        "recorded_qualification": recall.get(
            "history_conditioned_feedback_recall_qualified"
        ),
        "audit_scope": {
            "raw_model_output_included": False,
            "raw_prompt_included": False,
            "learning_claim": False,
            "authority": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cycle_dir", type=Path)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.cycle_dir, args.protocol)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(f"report_written={args.output}")
    else:
        print(encoded, end="")
    print(
        f"protocol_bound={report['protocol_binding_verified']};"
        f"receipt_links_verified={report['all_receipt_links_verified']};"
        f"protocol_criteria_met={report['all_protocol_criteria_met']};"
        "raw_output_included=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
