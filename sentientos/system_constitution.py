from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sentientos.attestation import append_jsonl, canonical_json_bytes, read_json, read_jsonl, write_json
from sentientos.constitution import INVARIANTS, INVARIANTS_BY_DOMAIN

CONSTITUTION_VERSION = 1
SYSTEM_CONSTITUTION_REL = Path("glow/constitution/system_constitution.json")
CONSTITUTION_SUMMARY_REL = Path("glow/constitution/constitution_summary.json")
CONSTITUTION_TRANSITIONS_REL = Path("glow/constitution/constitution_transitions.jsonl")

_MAX_RESTRICTION_CLASSES = 32
_MAX_ACTION_CLASSES = 64
_MAX_PATHS = 64
_MAX_PEER_ROLLUP = 128
_MAX_REASON_STACK = 16
_MAX_TRANSITIONS = 512


@dataclass(frozen=True)
class ConstitutionResolution:
    path: str
    payload: dict[str, object]
    present: bool
    required: bool


def _repo_root() -> Path:
    return Path(os.getenv("SENTIENTOS_REPO_ROOT", Path.cwd())).resolve()


def _rooted(root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def _resolve_json(root: Path, path: Path, *, required: bool) -> ConstitutionResolution:
    rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    payload = read_json(path)
    return ConstitutionResolution(path=rel, payload=payload, present=bool(payload), required=required)


def _sha256_path(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _domain_summary() -> dict[str, int]:
    return {domain: len(ids) for domain, ids in sorted(INVARIANTS_BY_DOMAIN.items())}


def _load_lines(path: Path, *, limit: int) -> list[dict[str, object]]:
    rows = read_jsonl(path)
    if len(rows) > limit:
        return rows[-limit:]
    return rows


def _restriction_classes(observability_rows: list[dict[str, object]]) -> list[str]:
    out: set[str] = set()
    for row in observability_rows:
        posture = row.get("runtime_posture")
        if not isinstance(posture, dict):
            continue
        reason_chain = posture.get("reason_chain")
        if isinstance(reason_chain, list):
            for reason in reason_chain:
                if isinstance(reason, dict) and isinstance(reason.get("restriction_class"), str):
                    value = str(reason["restriction_class"]).strip()
                    if value:
                        out.add(value)
    return sorted(out)[:_MAX_RESTRICTION_CLASSES]


def _action_classes(rollup: dict[str, object], budget: dict[str, object]) -> list[str]:
    classes: set[str] = set()
    for key in ("class_summary",):
        value = rollup.get(key)
        if isinstance(value, dict):
            classes.update(str(item) for item in value.keys())
    counts = budget.get("control_plane_task_counts")
    if isinstance(counts, dict):
        classes.update(str(item) for item in counts.keys())
    return sorted(value for value in classes if value)[:_MAX_ACTION_CLASSES]


def _peer_rollup(ledger: dict[str, object]) -> dict[str, object]:
    peer_states = ledger.get("peer_states")
    if not isinstance(peer_states, list):
        return {"peer_count": 0, "state_summary": {}, "peers": []}
    peers: list[dict[str, object]] = []
    for row in peer_states[:_MAX_PEER_ROLLUP]:
        if not isinstance(row, dict):
            continue
        peers.append(
            {
                "peer_id": row.get("peer_id"),
                "trust_state": row.get("trust_state"),
                "trust_reasons": list(row.get("trust_reasons", []))[:_MAX_REASON_STACK]
                if isinstance(row.get("trust_reasons"), list)
                else [],
                "reconciliation_needed": bool(row.get("reconciliation_needed", False)),
            }
        )
    return {
        "peer_count": int(ledger.get("peer_count", len(peers))) if isinstance(ledger.get("peer_count"), int) else len(peers),
        "state_summary": ledger.get("state_summary") if isinstance(ledger.get("state_summary"), dict) else {},
        "peers": peers,
    }


def _constitution_state(*, missing_required: bool, restricted: bool, degraded: bool) -> str:
    if missing_required:
        return "missing"
    if restricted:
        return "restricted"
    if degraded:
        return "degraded"
    return "healthy"


def _missing_required_artifacts(resolved: dict[str, ConstitutionResolution]) -> list[str]:
    missing: list[str] = []
    for name, item in sorted(resolved.items()):
        if item.required and not item.present:
            missing.append(name)
    return missing


def _restoration_hints(*, missing_required_artifacts: list[str], degraded_modes: list[str], restricted: bool) -> list[str]:
    hints: list[str] = []
    for artifact in missing_required_artifacts:
        if artifact == "audit_trust_state":
            hints.append("audit_trust_state missing: run python -m sentientos.start or python scripts/verify_audits.py --strict")
        elif artifact == "governor_rollup":
            hints.append("governor_rollup missing: run runtime governor once to emit glow/governor/rollup.json")
        elif artifact == "pulse_trust_epoch":
            hints.append("pulse_trust_epoch missing: run pulse trust epoch bootstrap to emit glow/pulse_trust/epoch_state.json")
        elif artifact in {"federation_governance_digest", "trust_ledger_state"}:
            hints.append("federation governance artifacts missing: run federated governance digest/trust-ledger update")
        elif artifact == "immutable_manifest":
            hints.append("immutable_manifest missing: run python scripts/generate_immutable_manifest.py")
    if restricted:
        hints.append("constitution is restricted; audit trust recovery or re-anchor may be required")
    if "runtime_posture_constrained" in degraded_modes:
        hints.append("runtime posture constrained: inspect governor reason_chain and pressure summary")
    return hints[:_MAX_REASON_STACK]


def _constitution_exit_code(*, missing_required: bool, restricted: bool, degraded: bool) -> int:
    if missing_required:
        return 3
    if restricted:
        return 2
    if degraded:
        return 1
    return 0


def _canonical_digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def compose_system_constitution(root: Path | None = None) -> dict[str, object]:
    repo_root = (root or _repo_root()).resolve()

    manifest_path = _rooted(repo_root, os.getenv("SENTIENTOS_IMMUTABLE_MANIFEST", "vow/immutable_manifest.json"))
    invariants_path = _rooted(repo_root, os.getenv("SENTIENTOS_INVARIANTS_PATH", "vow/invariants.yaml"))
    governance_policy_path = _rooted(repo_root, os.getenv("SENTIENTOS_GOVERNANCE_POLICY", "vow/governance_policy.yaml"))

    governor_root = _rooted(repo_root, os.getenv("SENTIENTOS_GOVERNOR_ROOT", "glow/governor"))
    federation_root = _rooted(repo_root, os.getenv("SENTIENTOS_FEDERATION_ROOT", "glow/federation"))
    epoch_state_path = _rooted(repo_root, os.getenv("PULSE_TRUST_EPOCH_STATE", "glow/pulse_trust/epoch_state.json"))

    resolved = {
        "immutable_manifest": _resolve_json(repo_root, manifest_path, required=True),
        "audit_trust_state": _resolve_json(repo_root, repo_root / "glow/runtime/audit_trust_state.json", required=False),
        "governor_rollup": _resolve_json(repo_root, governor_root / "rollup.json", required=False),
        "governor_budget": _resolve_json(repo_root, governor_root / "storm_budget.json", required=False),
        "governor_observability": _resolve_json(repo_root, governor_root / "observability.jsonl", required=False),
        "pulse_trust_epoch": _resolve_json(repo_root, epoch_state_path, required=False),
        "federation_governance_digest": _resolve_json(repo_root, federation_root / "governance_digest.json", required=False),
        "federation_quorum_policy": _resolve_json(repo_root, federation_root / "federation_quorum_policy.json", required=False),
        "federation_peer_digests": _resolve_json(repo_root, federation_root / "peer_governance_digests.json", required=False),
        "trust_ledger_state": _resolve_json(repo_root, federation_root / "trust_ledger_state.json", required=False),
        "trust_ledger_events": _resolve_json(repo_root, federation_root / "trust_ledger_events.jsonl", required=False),
        "audit_chain_report": _resolve_json(repo_root, repo_root / "glow/forge/audit_reports/latest.json", required=False),
    }

    observability_rows = _load_lines(governor_root / "observability.jsonl", limit=256)
    trust_event_rows = _load_lines(federation_root / "trust_ledger_events.jsonl", limit=128)

    rollup = resolved["governor_rollup"].payload
    budget = resolved["governor_budget"].payload
    audit = resolved["audit_trust_state"].payload
    epoch = resolved["pulse_trust_epoch"].payload
    governance_digest = resolved["federation_governance_digest"].payload
    trust_ledger = resolved["trust_ledger_state"].payload

    effective_posture = "unknown"
    posture_summary = rollup.get("runtime_posture_summary")
    if isinstance(posture_summary, dict):
        ranked = sorted(
            ((str(name), int(count)) for name, count in posture_summary.items() if isinstance(count, int)),
            key=lambda item: (-item[1], item[0]),
        )
        if ranked:
            effective_posture = ranked[0][0]

    degraded_modes: list[str] = []
    degraded_audit = bool(audit.get("degraded_audit_trust", False))
    if degraded_audit:
        degraded_modes.append("degraded_audit_trust")
    compromise_mode = bool(epoch.get("compromise_response_mode", False))
    if compromise_mode:
        degraded_modes.append("pulse_compromise_response_mode")
    if effective_posture == "constrained":
        degraded_modes.append("runtime_constrained")
    if effective_posture == "restricted":
        degraded_modes.append("runtime_restricted")

    trust_summary = trust_ledger.get("state_summary") if isinstance(trust_ledger.get("state_summary"), dict) else {}
    if isinstance(trust_summary, dict):
        for trust_state in ("watched", "degraded", "quarantined", "incompatible"):
            if isinstance(trust_summary.get(trust_state), int) and int(trust_summary.get(trust_state, 0)) > 0:
                degraded_modes.append(f"federation_peer_{trust_state}")

    missing_required_artifacts = _missing_required_artifacts(resolved)
    missing_required = bool(missing_required_artifacts)
    restricted = degraded_audit or effective_posture == "restricted" or compromise_mode
    degraded = bool(degraded_modes) and not restricted

    invariant_surface = {
        "invariant_count": len(INVARIANTS),
        "domain_counts": _domain_summary(),
        "invariants_path": str(invariants_path.relative_to(repo_root)) if invariants_path.is_relative_to(repo_root) else str(invariants_path),
        "invariants_sha256": _sha256_path(invariants_path),
    }

    layers = [
        "immutable_manifest",
        "invariant_surface",
        "audit_trust",
        "pulse_trust_epoch",
        "runtime_governor",
        "federated_governance",
        "trust_ledger",
    ]

    canonical_core: dict[str, object] = {
        "constitution_version": CONSTITUTION_VERSION,
        "constitution_state": _constitution_state(missing_required=missing_required, restricted=restricted, degraded=degraded),
        "immutable_manifest": {
            "path": resolved["immutable_manifest"].path,
            "manifest_sha256": _sha256_path(manifest_path),
            "manifest_identity": str(manifest_path),
        },
        "governance_policy": {
            "path": str(governance_policy_path.relative_to(repo_root)) if governance_policy_path.is_relative_to(repo_root) else str(governance_policy_path),
            "sha256": _sha256_path(governance_policy_path),
            "present": governance_policy_path.exists(),
        },
        "invariant_surface": invariant_surface,
        "audit_trust": {
            "status": audit.get("status", "unknown"),
            "history_state": audit.get("history_state", "unknown"),
            "degraded_audit_trust": degraded_audit,
            "checkpoint_id": audit.get("checkpoint_id"),
            "continuation_descends_from_anchor": audit.get("continuation_descends_from_anchor"),
            "trusted_history_head_hash": audit.get("trusted_history_head_hash"),
            "report_break_count": audit.get("report_break_count"),
            "trust_boundary_explicit": bool(audit.get("trust_boundary_explicit", False)),
        },
        "pulse_trust_epoch": {
            "active_epoch_id": epoch.get("active_epoch_id"),
            "compromise_response_mode": compromise_mode,
            "transition_counter": epoch.get("transition_counter"),
            "revoked_epoch_count": len(epoch.get("revoked_epochs", [])) if isinstance(epoch.get("revoked_epochs"), list) else 0,
        },
        "runtime_posture": {
            "governor_mode": rollup.get("mode", "unknown"),
            "effective_posture": effective_posture,
            "runtime_posture_summary": posture_summary if isinstance(posture_summary, dict) else {},
            "restriction_classes": _restriction_classes(observability_rows),
            "action_classes": _action_classes(rollup, budget),
        },
        "authority_layers": {
            "active_layers": layers,
            "governor_mode": rollup.get("mode", "unknown"),
        },
        "degraded_modes": sorted(set(degraded_modes))[:_MAX_REASON_STACK],
        "missing_required_artifacts": missing_required_artifacts,
        "federation_governance": {
            "governance_digest": governance_digest.get("digest"),
            "digest_components": governance_digest.get("components") if isinstance(governance_digest.get("components"), dict) else {},
            "quorum_policy": resolved["federation_quorum_policy"].payload,
            "peer_digests_summary": resolved["federation_peer_digests"].payload,
            "trust_ledger": _peer_rollup(trust_ledger),
            "recent_trust_events_count": len(trust_event_rows),
        },
        "constitutional_refs": {
            "artifact_paths": {
                name: {
                    "path": item.path,
                    "present": item.present,
                    "required": item.required,
                }
                for name, item in sorted(resolved.items())
            },
            "resolution_order": sorted(resolved.keys())[:_MAX_PATHS],
        },
    }

    digest = _canonical_digest(canonical_core)
    payload = dict(canonical_core)
    payload["constitutional_digest"] = digest
    payload["exit_code"] = _constitution_exit_code(missing_required=missing_required, restricted=restricted, degraded=degraded)
    payload["restoration_hints"] = _restoration_hints(
        missing_required_artifacts=missing_required_artifacts,
        degraded_modes=sorted(set(degraded_modes))[:_MAX_REASON_STACK],
        restricted=restricted,
    )
    payload["healthy"] = payload["constitution_state"] == "healthy"
    return payload


def write_constitution_artifacts(root: Path | None = None, *, payload: dict[str, object] | None = None) -> dict[str, object]:
    repo_root = (root or _repo_root()).resolve()
    resolved_payload = payload or compose_system_constitution(repo_root)

    system_path = repo_root / SYSTEM_CONSTITUTION_REL
    summary_path = repo_root / CONSTITUTION_SUMMARY_REL
    transitions_path = repo_root / CONSTITUTION_TRANSITIONS_REL

    write_json(system_path, resolved_payload)
    summary = {
        "constitution_version": resolved_payload.get("constitution_version"),
        "constitution_state": resolved_payload.get("constitution_state"),
        "constitutional_digest": resolved_payload.get("constitutional_digest"),
        "effective_posture": ((resolved_payload.get("runtime_posture") or {}) if isinstance(resolved_payload.get("runtime_posture"), dict) else {}).get("effective_posture"),
        "governor_mode": ((resolved_payload.get("runtime_posture") or {}) if isinstance(resolved_payload.get("runtime_posture"), dict) else {}).get("governor_mode"),
        "degraded_modes": list(resolved_payload.get("degraded_modes", []))[:_MAX_REASON_STACK],
        "missing_required_artifacts": list(resolved_payload.get("missing_required_artifacts", []))[:_MAX_REASON_STACK],
        "restoration_hints": list(resolved_payload.get("restoration_hints", []))[:_MAX_REASON_STACK],
        "exit_code": resolved_payload.get("exit_code"),
    }
    write_json(summary_path, summary)

    previous_digest: str | None = None
    rows = read_jsonl(transitions_path)
    if rows:
        tail = rows[-1]
        prev = tail.get("constitutional_digest") if isinstance(tail, dict) else None
        if isinstance(prev, str):
            previous_digest = prev

    transition = {
        "event": "constitution_regenerated",
        "transition": "changed" if previous_digest != resolved_payload.get("constitutional_digest") else "unchanged",
        "previous_digest": previous_digest,
        "constitutional_digest": resolved_payload.get("constitutional_digest"),
        "constitution_state": resolved_payload.get("constitution_state"),
        "exit_code": resolved_payload.get("exit_code"),
    }
    append_jsonl(transitions_path, transition)

    rows = read_jsonl(transitions_path)
    if len(rows) > _MAX_TRANSITIONS:
        with transitions_path.open("w", encoding="utf-8") as handle:
            for row in rows[-_MAX_TRANSITIONS:]:
                handle.write(json.dumps(row, sort_keys=True) + "\n")

    return {
        "system_constitution": str(SYSTEM_CONSTITUTION_REL),
        "constitution_summary": str(CONSTITUTION_SUMMARY_REL),
        "constitution_transitions": str(CONSTITUTION_TRANSITIONS_REL),
    }


def verify_constitution(root: Path | None = None) -> tuple[dict[str, object], int]:
    payload = compose_system_constitution(root)
    return payload, int(payload.get("exit_code", 3))


__all__ = [
    "compose_system_constitution",
    "write_constitution_artifacts",
    "verify_constitution",
    "SYSTEM_CONSTITUTION_REL",
    "CONSTITUTION_SUMMARY_REL",
    "CONSTITUTION_TRANSITIONS_REL",
]
