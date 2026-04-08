from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from sentientos.federation_canonical_execution import BOUNDED_FEDERATION_CANONICAL_ACTIONS


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _latest_row(rows: list[dict[str, Any]], *, correlation_id: str, typed_action_id: str) -> dict[str, Any] | None:
    for row in reversed(rows):
        if str(row.get("correlation_id") or "") != correlation_id:
            continue
        if str(row.get("typed_action_id") or "") != typed_action_id:
            continue
        return row
    return None


def resolve_bounded_federation_lifecycle(
    repo_root: Path,
    *,
    typed_action_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    if typed_action_id not in BOUNDED_FEDERATION_CANONICAL_ACTIONS:
        return {
            "typed_action_identity": typed_action_id,
            "correlation_id": correlation_id,
            "admission_disposition": "unknown",
            "execution_outcome": "unknown",
            "proof_linkage": "missing",
            "side_effect_semantics": "unknown",
            "canonical_lifecycle_state": "fragmented",
            "outcome_class": "fragmented_unresolved",
            "findings": [{"kind": "out_of_scope_typed_action", "surface": "bounded_federation_seed"}],
        }

    root = repo_root.resolve()
    canonical_rows = _read_jsonl(root / "glow/federation/canonical_execution.jsonl")
    ingest_rows = _read_jsonl(root / "glow/federation/ingest_classifications.jsonl")

    canonical_row = _latest_row(canonical_rows, correlation_id=correlation_id, typed_action_id=typed_action_id)
    ingest_row = _latest_row(ingest_rows, correlation_id=correlation_id, typed_action_id=typed_action_id)

    if canonical_row is None:
        findings.append({"kind": "canonical_execution_row_missing", "surface": "glow/federation/canonical_execution.jsonl"})
    if ingest_row is None:
        findings.append({"kind": "ingress_classification_row_missing", "surface": "glow/federation/ingest_classifications.jsonl"})

    canonical_outcome = str((canonical_row or {}).get("canonical_outcome") or "unknown")
    side_effect_status = str((canonical_row or {}).get("side_effect_status") or "unknown")
    admission_decision_ref = str((canonical_row or {}).get("admission_decision_ref") or "")

    proof_checks = [
        bool((canonical_row or {}).get("proof_linkage_present")),
        bool(admission_decision_ref),
        bool((ingest_row or {}).get("admission_decision_ref")),
        bool((ingest_row or {}).get("canonical_outcome")),
    ]
    proof_linkage = "present" if all(proof_checks) else "missing"

    if ingest_row is not None and canonical_row is not None:
        if str(ingest_row.get("admission_decision_ref") or "") != admission_decision_ref:
            findings.append({"kind": "ingress_canonical_admission_ref_mismatch", "surface": "glow/federation/ingest_classifications.jsonl"})
            proof_linkage = "missing"
        if str(ingest_row.get("canonical_outcome") or "") != canonical_outcome:
            findings.append({"kind": "ingress_canonical_outcome_mismatch", "surface": "glow/federation/ingest_classifications.jsonl"})
            proof_linkage = "missing"

    admission_disposition = "unknown"
    if canonical_outcome == "denied_pre_execution":
        admission_disposition = "denied"
    elif canonical_outcome in {"admitted_succeeded", "admitted_failed"}:
        admission_disposition = "admitted"

    outcome_class = "fragmented_unresolved"
    if canonical_outcome == "denied_pre_execution":
        if side_effect_status == "no_side_effect":
            outcome_class = "denied"
        else:
            findings.append({"kind": "denial_side_effect_semantics_fragmented", "surface": "glow/federation/canonical_execution.jsonl"})
    elif canonical_outcome == "admitted_failed":
        failure = (canonical_row or {}).get("failure")
        if isinstance(failure, dict) and str(failure.get("exception_type") or ""):
            outcome_class = "failed_after_admission"
        else:
            findings.append({"kind": "admitted_failure_payload_missing", "surface": "glow/federation/canonical_execution.jsonl:failure"})
    elif canonical_outcome == "admitted_succeeded":
        if side_effect_status in {"side_effect_committed", "no_side_effect"}:
            outcome_class = "success"
        else:
            findings.append({"kind": "success_side_effect_semantics_missing", "surface": "glow/federation/canonical_execution.jsonl:side_effect_status"})

    if proof_linkage != "present":
        findings.append({"kind": "proof_linkage_missing", "surface": "glow/federation/canonical_execution.jsonl+ingest_classifications.jsonl"})
        outcome_class = "fragmented_unresolved"

    return {
        "typed_action_identity": typed_action_id,
        "correlation_id": correlation_id,
        "admission_disposition": admission_disposition,
        "execution_outcome": canonical_outcome,
        "admission_decision_ref": admission_decision_ref,
        "proof_linkage": proof_linkage,
        "side_effect_semantics": side_effect_status,
        "canonical_lifecycle_state": "resolved" if outcome_class != "fragmented_unresolved" else "fragmented",
        "outcome_class": outcome_class,
        "findings": findings,
    }


def build_bounded_federation_trace_coherence_map(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    canonical_rows = _read_jsonl(root / "glow/federation/canonical_execution.jsonl")
    by_action: dict[str, list[dict[str, Any]]] = {action: [] for action in BOUNDED_FEDERATION_CANONICAL_ACTIONS}
    for row in canonical_rows:
        action_id = str(row.get("typed_action_id") or "")
        if action_id in by_action:
            by_action[action_id].append(row)

    per_intent: list[dict[str, Any]] = []
    outcome_counts: Counter[str] = Counter()
    for action_id in BOUNDED_FEDERATION_CANONICAL_ACTIONS:
        rows = by_action.get(action_id, [])
        correlations = sorted({str(row.get("correlation_id") or "") for row in rows if str(row.get("correlation_id") or "")})
        resolved = 0
        fragmented = 0
        proof_missing = 0
        local_outcomes: Counter[str] = Counter()
        for correlation_id in correlations:
            lifecycle = resolve_bounded_federation_lifecycle(root, typed_action_id=action_id, correlation_id=correlation_id)
            local_outcomes[str(lifecycle["outcome_class"])] += 1
            outcome_counts[str(lifecycle["outcome_class"])] += 1
            if lifecycle["canonical_lifecycle_state"] == "resolved":
                resolved += 1
            else:
                fragmented += 1
            if lifecycle["proof_linkage"] != "present":
                proof_missing += 1
        trace_state = "coherent_end_to_end"
        if not correlations:
            trace_state = "missing_stable_join"
        elif fragmented:
            trace_state = "partially_fragmented"
        per_intent.append(
            {
                "typed_action_id": action_id,
                "observed_correlations": len(correlations),
                "trace_state": trace_state,
                "lifecycle_resolved_count": resolved,
                "lifecycle_fragmented_count": fragmented,
                "proof_linkage_missing_count": proof_missing,
                "outcome_class_counts": dict(sorted(local_outcomes.items())),
            }
        )

    return {
        "bounded_typed_action_ids": list(BOUNDED_FEDERATION_CANONICAL_ACTIONS),
        "trace_coherence_map": per_intent,
        "outcome_class_counts": dict(sorted(outcome_counts.items())),
    }


__all__ = [
    "build_bounded_federation_trace_coherence_map",
    "resolve_bounded_federation_lifecycle",
]
