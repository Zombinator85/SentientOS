from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

ContradictionClass = Literal[
    "no_contradiction",
    "expected_degradation",
    "explainable_divergence",
    "policy_blocked_but_coherent",
    "missing_evidence_nonblocking",
    "contradiction_warning",
    "contradiction_blocking",
]

GateOutcome = Literal["pass", "pass_with_degradation", "warning", "blocking_failure", "indeterminate"]


@dataclass(frozen=True)
class PolicyThresholds:
    max_missing_nonblocking: int = 5
    max_warning_before_block: int = 2


def _classification(dimensions: dict[str, dict[str, object]], key: str) -> str:
    row = dimensions.get(key)
    if not isinstance(row, dict):
        return "missing_evidence"
    value = row.get("classification")
    return str(value) if isinstance(value, str) and value else "missing_evidence"


def _evidence(dimensions: dict[str, dict[str, object]], key: str) -> dict[str, object]:
    row = dimensions.get(key)
    if not isinstance(row, dict):
        return {}
    evidence = row.get("evidence")
    return evidence if isinstance(evidence, dict) else {}


def classify_contradictions(
    *,
    scenario: str,
    dimensions: dict[str, dict[str, object]],
    provenance: dict[str, object],
    oracle_contradictions: list[dict[str, object]],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []

    quorum_class = _classification(dimensions, "quorum_truth")
    digest_class = _classification(dimensions, "digest_truth")
    epoch_class = _classification(dimensions, "epoch_truth")
    replay_class = _classification(dimensions, "replay_truth")
    reanchor_class = _classification(dimensions, "reanchor_truth")
    fairness_class = _classification(dimensions, "fairness_truth")
    health_class = _classification(dimensions, "cluster_health_truth")

    quorum_evidence = _evidence(dimensions, "quorum_truth")
    replay_evidence = _evidence(dimensions, "replay_truth")

    if quorum_class == "consistent" and digest_class == "inconsistent":
        records.append(
            {
                "dimension": "quorum_vs_digest_posture",
                "classification": "contradiction_blocking",
                "reason": "quorum admitted while digest posture diverged",
            }
        )
    elif quorum_class == "blocked_by_policy" and digest_class in {"inconsistent", "degraded_but_explained"}:
        records.append(
            {
                "dimension": "quorum_vs_digest_posture",
                "classification": "policy_blocked_but_coherent",
                "reason": "policy blocked quorum and digest posture reflects fault handling",
            }
        )
    elif quorum_class in {"degraded_but_explained", "missing_evidence"} or digest_class in {"degraded_but_explained", "missing_evidence"}:
        records.append(
            {
                "dimension": "quorum_vs_digest_posture",
                "classification": "expected_degradation" if "degraded_but_explained" in {quorum_class, digest_class} else "missing_evidence_nonblocking",
                "reason": "quorum/digest posture degraded under WAN pressure",
            }
        )
    else:
        records.append({"dimension": "quorum_vs_digest_posture", "classification": "no_contradiction", "reason": "quorum and digest posture aligned"})

    if epoch_class == "inconsistent" and bool(quorum_evidence.get("admit", False)):
        records.append(
            {
                "dimension": "epoch_vs_peer_acceptance",
                "classification": "contradiction_warning",
                "reason": "epoch diverged while peers still admitted",
            }
        )
    elif epoch_class == "degraded_but_explained":
        records.append(
            {
                "dimension": "epoch_vs_peer_acceptance",
                "classification": "explainable_divergence" if "epoch_rotation" in scenario else "expected_degradation",
                "reason": "epoch divergence attributable to bounded WAN rotation",
            }
        )
    elif epoch_class == "missing_evidence":
        records.append(
            {
                "dimension": "epoch_vs_peer_acceptance",
                "classification": "missing_evidence_nonblocking",
                "reason": "epoch evidence incomplete",
            }
        )
    else:
        records.append({"dimension": "epoch_vs_peer_acceptance", "classification": "no_contradiction", "reason": "epoch and acceptance aligned"})

    replay_states = replay_evidence.get("replay_states")
    replay_state_rows = replay_states if isinstance(replay_states, list) else []
    if replay_class == "inconsistent" or "replay_contradicted" in {str(row) for row in replay_state_rows}:
        records.append(
            {
                "dimension": "replay_posture",
                "classification": "contradiction_blocking",
                "reason": "replay contradicted runtime evidence",
            }
        )
    elif int(replay_evidence.get("missing_but_expected") or 0) > 0:
        records.append(
            {
                "dimension": "replay_posture",
                "classification": "missing_evidence_nonblocking",
                "reason": "replay evidence expected-missing for bounded run",
            }
        )
    elif replay_class in {"degraded_but_explained", "missing_evidence"}:
        records.append(
            {
                "dimension": "replay_posture",
                "classification": "expected_degradation" if replay_class == "degraded_but_explained" else "missing_evidence_nonblocking",
                "reason": "replay evidence partial",
            }
        )
    else:
        records.append({"dimension": "replay_posture", "classification": "no_contradiction", "reason": "replay posture coherent"})

    if reanchor_class == "inconsistent":
        records.append(
            {
                "dimension": "reanchor_vs_cluster_trust",
                "classification": "contradiction_blocking",
                "reason": "reanchor continuation did not preserve trust chain",
            }
        )
    elif reanchor_class in {"degraded_but_explained", "blocked_by_policy"}:
        records.append(
            {
                "dimension": "reanchor_vs_cluster_trust",
                "classification": "explainable_divergence" if reanchor_class == "degraded_but_explained" else "policy_blocked_but_coherent",
                "reason": "reanchor posture coherent with bounded trust pressure",
            }
        )
    elif reanchor_class == "missing_evidence":
        records.append(
            {
                "dimension": "reanchor_vs_cluster_trust",
                "classification": "missing_evidence_nonblocking",
                "reason": "no reanchor evidence in scenario",
            }
        )
    else:
        records.append({"dimension": "reanchor_vs_cluster_trust", "classification": "no_contradiction", "reason": "reanchor continuation coherent"})

    if fairness_class == "inconsistent" and health_class == "consistent":
        records.append(
            {
                "dimension": "fairness_vs_cluster_health",
                "classification": "contradiction_warning",
                "reason": "fairness pressure diverged while cluster appears healthy",
            }
        )
    elif fairness_class in {"degraded_but_explained", "missing_evidence"} or health_class in {"degraded_but_explained", "missing_evidence"}:
        records.append(
            {
                "dimension": "fairness_vs_cluster_health",
                "classification": "expected_degradation" if "degraded_but_explained" in {fairness_class, health_class} else "missing_evidence_nonblocking",
                "reason": "fairness/health evidence degraded under WAN pressure",
            }
        )
    elif health_class == "inconsistent":
        records.append(
            {
                "dimension": "fairness_vs_cluster_health",
                "classification": "contradiction_blocking",
                "reason": "cluster health inconsistent",
            }
        )
    else:
        records.append({"dimension": "fairness_vs_cluster_health", "classification": "no_contradiction", "reason": "fairness and health coherent"})

    if not bool(provenance.get("digest_match")):
        records.append(
            {
                "dimension": "cluster_digest_vs_node_truth",
                "classification": "contradiction_blocking",
                "reason": "cluster final digest does not match recomputed node truth digest",
            }
        )
    else:
        records.append({"dimension": "cluster_digest_vs_node_truth", "classification": "no_contradiction", "reason": "cluster digest reconciled"})

    for row in oracle_contradictions:
        kind = str(row.get("kind") or "oracle_contradiction")
        detail = str(row.get("detail") or "")
        mapped: ContradictionClass = "contradiction_warning"
        if "mismatch" in kind or "runtime_vs_replay" in kind:
            mapped = "contradiction_blocking"
        if "expected_missing" in kind:
            mapped = "missing_evidence_nonblocking"
        records.append({"dimension": f"oracle:{kind}", "classification": mapped, "reason": detail})

    return records


def evaluate_release_gate(
    *,
    scenario: str,
    dimensions: dict[str, dict[str, object]],
    provenance: dict[str, object],
    oracle_contradictions: list[dict[str, object]],
    profile: str = "default",
) -> dict[str, object]:
    thresholds = PolicyThresholds()
    records = classify_contradictions(
        scenario=scenario,
        dimensions=dimensions,
        provenance=provenance,
        oracle_contradictions=oracle_contradictions,
    )

    counts: dict[str, int] = {}
    for row in records:
        key = str(row.get("classification") or "no_contradiction")
        counts[key] = counts.get(key, 0) + 1

    blocking = counts.get("contradiction_blocking", 0)
    warnings = counts.get("contradiction_warning", 0)
    missing = counts.get("missing_evidence_nonblocking", 0)
    degradations = counts.get("expected_degradation", 0) + counts.get("explainable_divergence", 0) + counts.get("policy_blocked_but_coherent", 0)

    outcome: GateOutcome = "pass"
    reason = "all contradiction dimensions coherent"
    if blocking > 0:
        outcome = "blocking_failure"
        reason = "blocking contradictions detected"
    elif warnings > thresholds.max_warning_before_block:
        outcome = "blocking_failure"
        reason = "warning contradictions exceeded bounded threshold"
    elif warnings > 0:
        outcome = "warning"
        reason = "warning-level contradictions detected"
    elif missing > thresholds.max_missing_nonblocking:
        outcome = "indeterminate"
        reason = "evidence gaps exceed bounded nonblocking threshold"
    elif degradations > 0 or missing > 0:
        outcome = "pass_with_degradation"
        reason = "only degradable contradictions observed"

    gate_exit_codes = {
        "pass": 0,
        "pass_with_degradation": 0,
        "warning": 1,
        "indeterminate": 2,
        "blocking_failure": 3,
    }
    digest = hashlib.sha256(
        json.dumps({"scenario": scenario, "profile": profile, "records": records, "counts": counts, "outcome": outcome}, sort_keys=True).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": 1,
        "scenario": scenario,
        "profile": profile,
        "thresholds": {
            "max_missing_nonblocking": thresholds.max_missing_nonblocking,
            "max_warning_before_block": thresholds.max_warning_before_block,
        },
        "counts": counts,
        "records": records,
        "outcome": outcome,
        "reason": reason,
        "gate_digest": digest,
        "exit_code": gate_exit_codes[outcome],
    }
