from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from sentientos.attestation import read_json, read_jsonl, write_json

TruthClassification = Literal[
    "consistent",
    "degraded_but_explained",
    "inconsistent",
    "missing_evidence",
    "blocked_by_policy",
]

TRUTH_DIMENSIONS: tuple[str, ...] = (
    "quorum_truth",
    "digest_truth",
    "epoch_truth",
    "replay_truth",
    "reanchor_truth",
    "fairness_truth",
    "cluster_health_truth",
)


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _first_present(data: dict[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        val = _as_str(data.get(key))
        if val:
            return val
    return None


def _bool(data: dict[str, object], key: str) -> bool | None:
    val = data.get(key)
    return val if isinstance(val, bool) else None


def _latest_replay(node_root: Path) -> tuple[dict[str, object], str | None]:
    replay_root = node_root / "glow/forge/replay"
    items = sorted(replay_root.glob("replay_*.json"), key=lambda path: path.name)
    if not items:
        return {}, None
    selected = items[-1]
    return read_json(selected), str(selected)


def _collect_node_evidence(*, node_root: Path, node_id: str, host_id: str) -> dict[str, object]:
    constitution = read_json(node_root / "glow/constitution/constitution_summary.json")
    quorum = read_json(node_root / "glow/federation/quorum_status.json")
    digest = read_json(node_root / "glow/federation/governance_digest.json")
    epoch = read_json(node_root / "glow/pulse_trust/epoch_state.json")
    governor = read_json(node_root / "glow/governor/rollup.json")
    audit_trust = read_json(node_root / "glow/runtime/audit_trust_state.json")
    identity = read_json(node_root / "glow/lab/node_identity.json")
    runtime_log = read_jsonl(node_root / "glow/lab/runtime_log.jsonl")
    replay, replay_path = _latest_replay(node_root)

    history_state = _first_present(audit_trust, ("history_state",))
    recovery_state = audit_trust.get("recovery_state") if isinstance(audit_trust.get("recovery_state"), dict) else {}
    if not history_state and isinstance(recovery_state, dict):
        history_state = _first_present(recovery_state, ("history_state",))

    continuation_descends = _bool(audit_trust, "continuation_descends_from_anchor")
    checkpoint_id = _first_present(audit_trust, ("checkpoint_id",))
    if isinstance(recovery_state, dict):
        if continuation_descends is None:
            continuation_descends = _bool(recovery_state, "continuation_descends_from_anchor")
        if checkpoint_id is None:
            checkpoint_id = _first_present(recovery_state, ("checkpoint_id",))

    return {
        "node_id": node_id,
        "host_id": host_id,
        "node_root": str(node_root),
        "identity": identity,
        "constitution": constitution,
        "quorum": quorum,
        "digest": digest,
        "epoch": epoch,
        "governor": governor,
        "audit_trust": audit_trust,
        "history_state": history_state,
        "checkpoint_id": checkpoint_id,
        "continuation_descends_from_anchor": continuation_descends,
        "runtime_log_tail": runtime_log[-20:],
        "replay": replay,
        "replay_path": replay_path,
    }


def _classify_quorum(node_rows: list[dict[str, object]], fault_types: set[str]) -> tuple[TruthClassification, dict[str, object]]:
    admits: list[bool] = []
    missing = 0
    for row in node_rows:
        quorum = row.get("quorum") if isinstance(row.get("quorum"), dict) else {}
        value = quorum.get("admit")
        if isinstance(value, bool):
            admits.append(value)
        else:
            missing += 1
    if not admits:
        return "missing_evidence", {"missing_nodes": missing}
    if len(set(admits)) == 1:
        if admits[0]:
            return "consistent", {"admit": True}
        if "peer_digest_mismatch" in fault_types or "trust_epoch_mismatch" in fault_types:
            return "blocked_by_policy", {"admit": False, "policy_faults": True}
        return "degraded_but_explained", {"admit": False}
    if {"host_partition", "asymmetric_loss"}.intersection(fault_types):
        return "degraded_but_explained", {"admits": admits}
    return "inconsistent", {"admits": admits}


def _classify_digest(node_rows: list[dict[str, object]], fault_types: set[str]) -> tuple[TruthClassification, dict[str, object]]:
    digests = [
        _first_present(row.get("digest") if isinstance(row.get("digest"), dict) else {}, ("digest", "governance_digest", "constitutional_digest"))
        for row in node_rows
    ]
    present = sorted({item for item in digests if item})
    if not present:
        return "missing_evidence", {"missing_nodes": len(node_rows)}
    if len(present) == 1:
        return "consistent", {"digest": present[0]}
    if "peer_digest_mismatch" in fault_types:
        return "degraded_but_explained", {"digests": present}
    return "inconsistent", {"digests": present}


def _classify_epoch(node_rows: list[dict[str, object]], fault_types: set[str]) -> tuple[TruthClassification, dict[str, object]]:
    epochs = [
        _first_present(row.get("epoch") if isinstance(row.get("epoch"), dict) else {}, ("active_epoch_id", "epoch_id"))
        for row in node_rows
    ]
    present = sorted({item for item in epochs if item})
    if not present:
        return "missing_evidence", {"missing_nodes": len(node_rows)}
    if len(present) == 1:
        return "consistent", {"epoch": present[0]}
    if "epoch_rotate" in fault_types or "wan_epoch_rotation_under_partition" in fault_types:
        return "degraded_but_explained", {"epochs": present}
    return "inconsistent", {"epochs": present}


def _classify_replay(node_rows: list[dict[str, object]]) -> tuple[TruthClassification, dict[str, object]]:
    statuses: list[str] = []
    missing = 0
    for row in node_rows:
        replay = row.get("replay") if isinstance(row.get("replay"), dict) else {}
        if not replay:
            missing += 1
            continue
        verdict = _as_str(replay.get("integrity_overall")) or _as_str(replay.get("status")) or "unknown"
        statuses.append(verdict)
    if not statuses and missing:
        return "missing_evidence", {"missing_nodes": missing}
    bad = [item for item in statuses if item in {"fail", "failed", "inconsistent"}]
    if bad:
        return "inconsistent", {"statuses": statuses}
    if missing:
        return "degraded_but_explained", {"statuses": statuses, "missing_nodes": missing}
    return "consistent", {"statuses": statuses}


def _classify_reanchor(node_rows: list[dict[str, object]], fault_types: set[str]) -> tuple[TruthClassification, dict[str, object]]:
    has_break = any(str(row.get("history_state") or "") == "broken_preserved" for row in node_rows)
    continuations = [
        bool(row.get("continuation_descends_from_anchor"))
        for row in node_rows
        if row.get("checkpoint_id") is not None or row.get("history_state") is not None
    ]
    checkpoint_count = sum(1 for row in node_rows if row.get("checkpoint_id"))
    if not has_break and not continuations and "force_reanchor" not in fault_types:
        return "missing_evidence", {"reason": "no_reanchor_activity"}
    if has_break and checkpoint_count == 0:
        return "inconsistent", {"has_break": has_break, "checkpoint_count": checkpoint_count}
    if continuations and all(continuations):
        return "consistent", {"checkpoint_count": checkpoint_count, "continuations": continuations}
    if continuations:
        return "degraded_but_explained", {"checkpoint_count": checkpoint_count, "continuations": continuations}
    return "missing_evidence", {"checkpoint_count": checkpoint_count}


def _classify_fairness(transitions: list[dict[str, object]], host_ids: list[str]) -> tuple[TruthClassification, dict[str, object]]:
    starts: dict[str, int] = {host_id: 0 for host_id in host_ids}
    stops: dict[str, int] = {host_id: 0 for host_id in host_ids}
    exit_codes: list[int] = []
    for row in transitions:
        host_id = _as_str(row.get("host_id"))
        if not host_id:
            continue
        if str(row.get("state") or "") == "running":
            starts[host_id] = starts.get(host_id, 0) + 1
        if str(row.get("state") or "") == "stopped":
            stops[host_id] = stops.get(host_id, 0) + 1
            code = row.get("exit_code")
            if isinstance(code, int):
                exit_codes.append(code)
    if not transitions:
        return "missing_evidence", {"reason": "no_transitions"}
    if all(code == 0 for code in exit_codes) and starts == stops:
        return "consistent", {"starts": starts, "stops": stops, "exit_codes": exit_codes}
    impacted = [host for host in host_ids if starts.get(host, 0) != stops.get(host, 0)]
    if len(impacted) <= 1:
        return "degraded_but_explained", {"starts": starts, "stops": stops, "exit_codes": exit_codes}
    return "inconsistent", {"starts": starts, "stops": stops, "exit_codes": exit_codes}


def _classify_cluster_health(node_rows: list[dict[str, object]]) -> tuple[TruthClassification, dict[str, object]]:
    states = [
        _first_present(row.get("health") if isinstance(row.get("health"), dict) else {}, ("health_state",)) or "missing"
        for row in node_rows
    ]
    unique = sorted(set(states))
    if unique == ["healthy"]:
        return "consistent", {"states": states}
    if any(state in {"restricted", "missing"} for state in unique):
        return "inconsistent", {"states": states}
    return "degraded_but_explained", {"states": states}


def reconcile_provenance(
    *,
    run_root: Path,
    scenario: str,
    topology: str,
    seed: int,
    node_rows: list[dict[str, object]],
) -> dict[str, object]:
    timeline = read_json(run_root / "fault_timeline.json")
    transitions = read_jsonl(run_root / "host_process_transitions.jsonl")
    faults = read_jsonl(run_root / "wan_faults.jsonl")
    final_cluster = read_json(run_root / "final_cluster_digest.json")

    schedule_rows = timeline.get("timeline") if isinstance(timeline.get("timeline"), list) else []
    schedule_id = hashlib.sha256(json.dumps(schedule_rows, sort_keys=True).encode("utf-8")).hexdigest()

    correlations: list[dict[str, object]] = []
    digest_rows: list[str] = []
    for row in sorted(node_rows, key=lambda item: (str(item.get("host_id")), str(item.get("node_id")))):
        trust = row.get("epoch") if isinstance(row.get("epoch"), dict) else {}
        digest_rows.append(json.dumps(trust, sort_keys=True))
        identity = row.get("identity") if isinstance(row.get("identity"), dict) else {}
        correlations.append(
            {
                "host_id": row.get("host_id"),
                "node_id": row.get("node_id"),
                "scenario_id": identity.get("scenario"),
                "seed": identity.get("seed"),
                "topology": identity.get("topology"),
                "fault_schedule_id": schedule_id,
                "replay_path": row.get("replay_path"),
                "checkpoint_id": row.get("checkpoint_id"),
            }
        )

    recomputed_digest = hashlib.sha256("\n".join(sorted(digest_rows)).encode("utf-8")).hexdigest()
    claimed_digest = _as_str(final_cluster.get("digest"))
    digest_match = claimed_digest == recomputed_digest if claimed_digest else False

    timeline_events: list[dict[str, object]] = []
    for row in faults:
        timeline_events.append(
            {
                "source": "fault",
                "offset_s": row.get("offset_s"),
                "host_id": row.get("host_id"),
                "node_id": row.get("node_id"),
                "type": row.get("type"),
            }
        )
    base_ts = min((ts for ts in (_parse_ts(row.get("ts")) for row in transitions) if ts is not None), default=None)
    for row in transitions:
        ts = _parse_ts(row.get("ts"))
        delta = (ts - base_ts).total_seconds() if ts is not None and base_ts is not None else None
        timeline_events.append(
            {
                "source": "process",
                "offset_s": round(delta, 3) if isinstance(delta, float) else None,
                "host_id": row.get("host_id"),
                "node_id": row.get("node_id"),
                "state": row.get("state"),
            }
        )

    timeline_events.sort(
        key=lambda item: (
            99999.0 if item.get("offset_s") is None else float(item["offset_s"]),
            str(item.get("source")),
            str(item.get("host_id")),
            str(item.get("node_id")),
        )
    )

    identity_ok = all(
        row.get("scenario_id") == scenario and row.get("topology") == topology and int(row.get("seed") or -1) == seed
        for row in correlations
    )
    status: TruthClassification
    if not correlations:
        status = "missing_evidence"
    elif identity_ok and digest_match:
        status = "consistent"
    elif identity_ok:
        status = "inconsistent"
    else:
        status = "degraded_but_explained"

    return {
        "schema_version": 1,
        "status": status,
        "fault_schedule_id": schedule_id,
        "digest_match": digest_match,
        "claimed_cluster_digest": claimed_digest,
        "recomputed_cluster_digest": recomputed_digest,
        "identity_aligned": identity_ok,
        "node_correlations": correlations,
        "timeline": timeline_events,
    }


def run_truth_oracle(
    *,
    run_root: Path,
    scenario: str,
    topology: str,
    seed: int,
    hosts: list[dict[str, object]],
    nodes: list[dict[str, object]],
) -> dict[str, object]:
    node_evidence: list[dict[str, object]] = []
    for row in nodes:
        node_id = str(row.get("node_id") or "")
        host_id = str(row.get("host_id") or "")
        host_row = next((host for host in hosts if str(host.get("host_id")) == host_id), None)
        if host_row is None:
            continue
        node_root = Path(str(host_row.get("runtime_root"))) / "nodes" / node_id
        node_evidence.append(_collect_node_evidence(node_root=node_root, node_id=node_id, host_id=host_id))

    faults = read_jsonl(run_root / "wan_faults.jsonl")
    fault_types = {str(row.get("type")) for row in faults if isinstance(row.get("type"), str)}
    transitions = read_jsonl(run_root / "host_process_transitions.jsonl")

    dimensions: dict[str, dict[str, object]] = {}
    quorum_truth, quorum_evidence = _classify_quorum(node_evidence, fault_types)
    dimensions["quorum_truth"] = {"classification": quorum_truth, "evidence": quorum_evidence}
    digest_truth, digest_evidence = _classify_digest(node_evidence, fault_types)
    dimensions["digest_truth"] = {"classification": digest_truth, "evidence": digest_evidence}
    epoch_truth, epoch_evidence = _classify_epoch(node_evidence, fault_types)
    dimensions["epoch_truth"] = {"classification": epoch_truth, "evidence": epoch_evidence}
    replay_truth, replay_evidence = _classify_replay(node_evidence)
    dimensions["replay_truth"] = {"classification": replay_truth, "evidence": replay_evidence}
    reanchor_truth, reanchor_evidence = _classify_reanchor(node_evidence, fault_types)
    dimensions["reanchor_truth"] = {"classification": reanchor_truth, "evidence": reanchor_evidence}
    fairness_truth, fairness_evidence = _classify_fairness(transitions, [str(host.get("host_id")) for host in hosts])
    dimensions["fairness_truth"] = {"classification": fairness_truth, "evidence": fairness_evidence}
    health_truth, health_evidence = _classify_cluster_health(node_evidence)
    dimensions["cluster_health_truth"] = {"classification": health_truth, "evidence": health_evidence}

    provenance = reconcile_provenance(run_root=run_root, scenario=scenario, topology=topology, seed=seed, node_rows=node_evidence)

    contradictions: list[dict[str, object]] = []
    if provenance.get("status") == "inconsistent":
        contradictions.append({"kind": "provenance_mismatch", "detail": "cluster digest mismatch"})
    if dimensions["cluster_health_truth"]["classification"] == "consistent" and dimensions["replay_truth"]["classification"] == "inconsistent":
        contradictions.append({"kind": "runtime_vs_replay", "detail": "runtime appears healthy but replay failed"})

    score_weights = {
        "consistent": 1,
        "degraded_but_explained": 0,
        "blocked_by_policy": 0,
        "missing_evidence": -1,
        "inconsistent": -2,
    }
    truth_score = sum(score_weights.get(str(row.get("classification")), -2) for row in dimensions.values())
    cluster_truth = "consistent" if truth_score >= len(TRUTH_DIMENSIONS) - 1 else "degraded_but_explained" if truth_score >= 0 else "inconsistent"

    evidence_manifest = {
        "schema_version": 1,
        "run_root": str(run_root),
        "node_evidence": [
            {
                "node_id": row.get("node_id"),
                "host_id": row.get("host_id"),
                "node_root": row.get("node_root"),
                "replay_path": row.get("replay_path"),
                "checkpoint_id": row.get("checkpoint_id"),
            }
            for row in node_evidence
        ],
        "fault_log": str(run_root / "wan_faults.jsonl"),
        "process_transitions": str(run_root / "host_process_transitions.jsonl"),
    }

    oracle_root = run_root / "wan_truth"
    oracle_root.mkdir(parents=True, exist_ok=True)
    write_json(oracle_root / "truth_dimensions.json", {"schema_version": 1, "dimensions": dimensions})
    write_json(oracle_root / "provenance_reconciliation.json", provenance)
    write_json(oracle_root / "evidence_manifest.json", evidence_manifest)
    write_json(oracle_root / "contradictions_report.json", {"schema_version": 1, "contradictions": contradictions})

    final_digest = hashlib.sha256(
        json.dumps({"dimensions": dimensions, "provenance": provenance, "contradictions": contradictions}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    write_json(oracle_root / "cluster_final_truth_digest.json", {"schema_version": 1, "truth_digest": final_digest, "cluster_truth": cluster_truth})

    summary = {
        "schema_version": 1,
        "cluster_truth": cluster_truth,
        "truth_score": truth_score,
        "dimension_classifications": {key: row.get("classification") for key, row in dimensions.items()},
        "provenance_status": provenance.get("status"),
        "contradictions": contradictions,
        "artifact_root": str(oracle_root),
    }
    write_json(oracle_root / "truth_oracle_summary.json", summary)

    return {
        "summary": summary,
        "dimensions": dimensions,
        "provenance": provenance,
        "evidence_manifest": evidence_manifest,
        "contradictions": contradictions,
        "truth_digest": final_digest,
        "artifact_paths": {
            "truth_oracle_summary": str(oracle_root / "truth_oracle_summary.json"),
            "provenance_reconciliation": str(oracle_root / "provenance_reconciliation.json"),
            "truth_dimensions": str(oracle_root / "truth_dimensions.json"),
            "evidence_manifest": str(oracle_root / "evidence_manifest.json"),
            "cluster_final_truth_digest": str(oracle_root / "cluster_final_truth_digest.json"),
            "contradictions_report": str(oracle_root / "contradictions_report.json"),
        },
    }
