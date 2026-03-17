from __future__ import annotations

from pathlib import Path
from typing import Any

from sentientos.attestation import iso_now, read_json, read_jsonl, write_json

REQUIRED_DIMENSIONS: tuple[str, ...] = (
    "quorum_state",
    "digest_state",
    "epoch_state",
    "reanchor_state",
    "fairness_state",
    "health_state",
)
OPTIONAL_DIMENSIONS: tuple[str, ...] = ("replay_state",)


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _latest_replay_summary(node_root: Path) -> dict[str, object]:
    replay_runs = read_jsonl(node_root / "pulse/replay_runs.jsonl")
    if replay_runs:
        row = replay_runs[-1]
        return {
            "state": "replay_confirmed" if str(row.get("integrity_status") or "") in {"ok", "warn"} else "replay_contradicted",
            "integrity_status": row.get("integrity_status"),
            "path": row.get("path"),
            "exit_code": row.get("exit_code"),
            "requested": True,
        }

    replay_root = node_root / "glow/forge/replay"
    replay_items = sorted(replay_root.glob("replay_*.json"), key=lambda item: item.name)
    if replay_items:
        payload = read_json(replay_items[-1])
        status = _as_str(payload.get("integrity_overall")) or _as_str(payload.get("status")) or "unknown"
        state = "replay_confirmed" if status in {"ok", "warn"} else "replay_contradicted" if status in {"fail", "failed", "inconsistent"} else "replay_compatible_evidence"
        return {
            "state": state,
            "integrity_status": status,
            "path": str(replay_items[-1]),
            "exit_code": payload.get("exit_code"),
            "requested": True,
        }

    return {
        "state": "no_replay_evidence_requested",
        "requested": False,
    }


def emit_node_truth_artifacts(node_root: Path, *, node_id: str, host_id: str) -> dict[str, object]:
    health = read_json(node_root / "glow/operators/node_health.json")
    quorum = read_json(node_root / "glow/federation/quorum_status.json")
    digest = read_json(node_root / "glow/federation/governance_digest.json")
    epoch = read_json(node_root / "glow/pulse_trust/epoch_state.json")
    audit = read_json(node_root / "glow/runtime/audit_trust_state.json")
    wan_status = read_json(node_root / "glow/lab/wan_status.json")
    runtime_tail = read_jsonl(node_root / "glow/lab/runtime_log.jsonl")[-20:]

    pending_votes = quorum.get("pending_votes") if isinstance(quorum.get("pending_votes"), int) else 0
    observed_peers = digest.get("peer_observations") if isinstance(digest.get("peer_observations"), list) else []
    mismatched = [row for row in observed_peers if isinstance(row, dict) and bool(row.get("compatible") is False)]

    recovery = audit.get("recovery_state") if isinstance(audit.get("recovery_state"), dict) else {}
    history_state = _as_str(audit.get("history_state")) or _as_str(recovery.get("history_state")) or "unknown"
    checkpoint_id = _as_str(audit.get("checkpoint_id")) or _as_str(recovery.get("checkpoint_id"))
    continuation = audit.get("continuation_descends_from_anchor")
    if not isinstance(continuation, bool):
        continuation = recovery.get("continuation_descends_from_anchor")
    continuation = continuation if isinstance(continuation, bool) else None

    starvation = 0
    noisy_subjects = 0
    for row in runtime_tail:
        if str(row.get("health_state") or "") in {"degraded", "restricted", "missing"}:
            starvation += 1
        if str(row.get("integrity_overall") or "") in {"warn", "fail"}:
            noisy_subjects += 1

    epoch_state = {
        "active_epoch_id": _as_str(epoch.get("active_epoch_id")) or _as_str(epoch.get("epoch_id")),
        "retired_epoch_ids": epoch.get("retired_epoch_ids") if isinstance(epoch.get("retired_epoch_ids"), list) else [],
        "revoked_epoch_ids": epoch.get("revoked_epoch_ids") if isinstance(epoch.get("revoked_epoch_ids"), list) else [],
        "classification": "active",
    }
    if epoch_state["revoked_epoch_ids"]:
        epoch_state["classification"] = "revoked_present"
    elif epoch_state["retired_epoch_ids"]:
        epoch_state["classification"] = "retired_present"

    replay = _latest_replay_summary(node_root)

    evidence = {
        "schema_version": 1,
        "ts": iso_now(),
        "node_id": node_id,
        "host_id": host_id,
        "contract": {
            "required_dimensions": list(REQUIRED_DIMENSIONS),
            "optional_dimensions": list(OPTIONAL_DIMENSIONS),
        },
        "quorum_state": {
            "admit": quorum.get("admit") if isinstance(quorum.get("admit"), bool) else None,
            "pending_votes": pending_votes,
            "posture": "pending" if pending_votes > 0 else "decided",
        },
        "digest_state": {
            "digest": _as_str(digest.get("digest")) or _as_str(digest.get("governance_digest")) or _as_str(digest.get("constitutional_digest")),
            "peer_observations": observed_peers[:64],
            "mismatch_count": len(mismatched),
            "posture": "compatible" if not mismatched else "mismatch_observed",
        },
        "epoch_state": epoch_state,
        "reanchor_state": {
            "history_state": history_state,
            "checkpoint_id": checkpoint_id,
            "continuation_descends_from_anchor": continuation,
            "posture": "continuation_verified" if continuation else "continuation_missing" if checkpoint_id else "no_reanchor_activity",
        },
        "fairness_state": {
            "runtime_samples": len(runtime_tail),
            "starvation_signals": starvation,
            "noisy_subjects": noisy_subjects,
            "posture": "balanced" if starvation == 0 else "degraded_signals",
        },
        "health_state": {
            "health_state": _as_str(health.get("health_state")) or "missing",
            "constitution_state": _as_str(health.get("constitution_state")) or "missing",
            "integrity_overall": _as_str(health.get("integrity_overall")) or "missing",
            "wan_network_state": _as_str(wan_status.get("network_state")) or "unknown",
        },
        "replay_state": replay,
        "completeness": {
            "required_present": [],
            "required_missing": [],
            "optional_present": [],
        },
    }

    for key in REQUIRED_DIMENSIONS:
        if isinstance(evidence.get(key), dict) and evidence.get(key):
            evidence["completeness"]["required_present"].append(key)
        else:
            evidence["completeness"]["required_missing"].append(key)
    for key in OPTIONAL_DIMENSIONS:
        if isinstance(evidence.get(key), dict) and evidence.get(key):
            evidence["completeness"]["optional_present"].append(key)

    write_json(node_root / "glow/lab/node_truth_artifacts.json", evidence)
    return evidence
