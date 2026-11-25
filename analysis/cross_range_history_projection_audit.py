"""Audit persisted cross-range history evidence without invoking a model.

This pre-inference audit reports score-bound history projections and the
independent-input-anchor gate for source and target task families. It cannot
establish prompt delivery, model use, task correctness, learning, or causality.
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

from sentientos.local_model_authority import digest_payload  # noqa: E402
from sentientos.resident_developmental_cognition import (  # noqa: E402
    audit_task_family_history_projection,
)


def _family_projection(candidates: list[dict[str, Any]], family: str) -> dict[str, Any]:
    relevant = [candidate for candidate in candidates
        if any(isinstance(fact, dict)
            and isinstance(fact.get("payload"), dict)
            and fact["payload"].get("objective_task_family") == family
            for fact in candidate.get("selected_facts", []))]
    audit = audit_task_family_history_projection(relevant,
        task_family_id=family, target_model_identity=None)
    anchors = audit["independent_input_anchor_coverage"]
    return {
        "task_family_id": family,
        "candidate_record_count": len(relevant),
        "projectable_experience_count": audit["projectable_experience_count"],
        "projectable_source_run_count": audit["projectable_source_run_count"],
        "correct_example_count": audit["correct_example_count"],
        "independent_input_anchor_coverage": {
            "status": anchors["status"],
            "correct_source_run_count": anchors["correct_source_run_count"],
            "distinct_correct_input_count": anchors["distinct_correct_input_count"],
            "candidate_anchor_pair_count": anchors["candidate_anchor_pair_count"],
            "conflicting_correct_input_count": anchors[
                "conflicting_correct_input_count"],
            "minimum_requirements": anchors["minimum_requirements"],
        },
        "historical_only": True,
        "current_truth": False,
        "authority": False,
    }


def create_audit(*, history_records: Path, source_family: str,
        target_family: str) -> dict[str, Any]:
    if (not history_records.is_dir() or history_records.is_symlink()
            or not re.fullmatch(r"[a-z0-9_]{1,100}", source_family)
            or not re.fullmatch(r"[a-z0-9_]{1,100}", target_family)
            or source_family == target_family):
        raise ValueError("cross_range_history_audit_input_invalid")
    files = sorted(history_records.glob("devrec-*.json"))
    if not files or len(files) > 10000:
        raise ValueError("cross_range_history_audit_record_count_invalid")
    candidates: list[dict[str, Any]] = []
    file_digests: list[dict[str, str]] = []
    for path in files:
        if path.is_symlink() or not path.is_file() or not re.fullmatch(
                r"devrec-[0-9a-f]{24}\.json", path.name):
            raise ValueError("cross_range_history_audit_record_invalid")
        raw = path.read_bytes()
        record = json.loads(raw.decode("utf-8"))
        candidate = record.get("candidate") if isinstance(record, dict) else None
        if not isinstance(candidate, dict):
            raise ValueError("cross_range_history_audit_candidate_missing")
        candidates.append(candidate)
        file_digests.append({"name": path.name,
            "sha256": hashlib.sha256(raw).hexdigest()})
    source = _family_projection(candidates, source_family)
    target = _family_projection(candidates, target_family)
    source_anchors = source["independent_input_anchor_coverage"]
    target_anchors = target["independent_input_anchor_coverage"]
    source_ready = source_anchors["status"] == "independent_correct_input_anchor_available"
    target_ready = target_anchors["status"] == "independent_correct_input_anchor_available"
    result: dict[str, Any] = {
        "schema_version": "sentientos.cross_range_history_projection_audit:v1",
        "analysis_timing": "posthoc_preinference_history_projection_audit",
        "status": ("source_history_anchor_gate_available" if source_ready else
            "source_history_anchor_gate_not_available"),
        "source_family": source,
        "target_family": target,
        "target_family_anchor_gate_available": target_ready,
        "history_records_file_count": len(file_digests),
        "history_records_manifest_digest": digest_payload(file_digests),
        "source_score_binding_accepted_by_projection_auditor": True,
        "prompt_delivery_verified": False,
        "all_family_probe_overlap_checked": False,
        "inference_performed": False,
        "capability_evaluated": False,
        "learning_established": False,
        "causal_claim_made": False,
        "authority_granted": False,
    }
    result["audit_digest"] = digest_payload(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-records", type=Path, required=True)
    parser.add_argument("--source-family", required=True)
    parser.add_argument("--target-family", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = create_audit(history_records=args.history_records,
        source_family=args.source_family, target_family=args.target_family)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({"artifact": str(args.output), "status": result["status"],
        "audit_digest": result["audit_digest"], "inference_performed": False},
        sort_keys=True))


if __name__ == "__main__":
    main()
