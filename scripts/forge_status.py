from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from sentientos import artifact_catalog
from sentientos.attestation import canonical_json_bytes, read_json, read_jsonl
from sentientos.attestation_snapshot import SIGNATURE_INDEX_PATH, SNAPSHOT_DIR, SNAPSHOT_PULSE_PATH, should_emit_snapshot


@dataclass(frozen=True)
class ResolvedArtifact:
    payload: dict[str, object]
    path: str | None
    resolution: str


def _latest_json_from_glob(root: Path, pattern: str) -> tuple[dict[str, object], str | None]:
    items = sorted(root.glob(pattern), key=lambda item: item.name)
    if not items:
        return {}, None
    path = items[-1]
    return read_json(path), str(path.relative_to(root))


def _resolve_catalog_then_disk(root: Path, *, kind: str, disk_glob: str) -> ResolvedArtifact:
    entry = artifact_catalog.latest(root, kind)
    if entry is not None:
        payload = artifact_catalog.load_catalog_artifact(root, entry)
        resolved = artifact_catalog.resolve_entry_path(root, entry)
        if payload:
            return ResolvedArtifact(payload=payload, path=resolved, resolution="catalog")
    payload, path = _latest_json_from_glob(root, disk_glob)
    return ResolvedArtifact(payload=payload, path=path, resolution="disk")


def _resolve_integrity(root: Path) -> ResolvedArtifact:
    return _resolve_catalog_then_disk(root, kind="integrity_status", disk_glob="glow/forge/integrity/status_*.json")


def _resolve_snapshot(root: Path) -> ResolvedArtifact:
    resolved = _resolve_catalog_then_disk(root, kind="attestation_snapshot", disk_glob=str(SNAPSHOT_DIR / "snapshot_*.json"))
    if resolved.payload:
        return resolved
    rows = read_jsonl(root / SNAPSHOT_PULSE_PATH)
    for row in reversed(rows):
        rel = row.get("path")
        if isinstance(rel, str):
            payload = read_json(root / rel)
            if payload:
                return ResolvedArtifact(payload=payload, path=rel, resolution="disk")
    return resolved


def _resolve_witness_status(root: Path) -> ResolvedArtifact:
    entry = artifact_catalog.latest(root, "witness_publish")
    if entry is not None:
        payload = artifact_catalog.load_catalog_artifact(root, entry)
        if payload:
            return ResolvedArtifact(payload=payload, path=artifact_catalog.resolve_entry_path(root, entry), resolution="catalog")
    return ResolvedArtifact(payload=read_json(root / "glow/federation/anchor_witness_status.json"), path="glow/federation/anchor_witness_status.json", resolution="disk")


def _signature_tip(root: Path) -> dict[str, object]:
    rows = read_jsonl(root / SIGNATURE_INDEX_PATH)
    if not rows:
        return {"sig_hash": None, "path": str(SIGNATURE_INDEX_PATH), "status": "missing"}
    latest = rows[-1]
    sig_hash = latest.get("sig_hash") if isinstance(latest.get("sig_hash"), str) else None
    return {"sig_hash": sig_hash, "path": str(SIGNATURE_INDEX_PATH), "status": "present"}


def _map_signature_streams(integrity: dict[str, object]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    gates = integrity.get("gate_results")
    gate_map: dict[str, dict[str, object]] = {}
    if isinstance(gates, list):
        for gate in gates:
            if isinstance(gate, dict) and isinstance(gate.get("name"), str):
                gate_map[str(gate["name"])] = gate
    for key, gate_name in {
        "strategic": "strategic_signatures",
        "rollup": "rollup_signatures",
        "snapshot": "attestation_snapshot_signatures",
    }.items():
        gate = gate_map.get(gate_name, {})
        status = str(gate.get("status") or "skipped")
        reason = str(gate.get("reason") or "not_evaluated")
        out[key] = {"status": status, "reason": reason}
    return out


def _snapshot_cadence(root: Path, integrity: dict[str, object], snapshot: dict[str, object], integrity_hash: str) -> dict[str, object]:
    if not integrity:
        return {"emitted": bool(snapshot), "reason": "integrity_status_missing"}
    if not snapshot:
        return {"emitted": False, "reason": "snapshot_missing"}
    min_interval = max(1, int(os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_MIN_INTERVAL_SECONDS", "600")))
    can_emit = should_emit_snapshot(
        root,
        ts=str(integrity.get("ts") or ""),
        integrity_status_hash=integrity_hash,
        policy_hash=str(integrity.get("policy_hash") or ""),
        goal_graph_hash=None,
        min_interval_seconds=min_interval,
    )
    return {
        "emitted": bool(snapshot),
        "reason": "eligible_to_emit" if can_emit else "cadence_not_elapsed",
        "last_emit_ts": snapshot.get("ts"),
    }


def build_status_payload(root: Path) -> dict[str, object]:
    integrity = _resolve_integrity(root)
    snapshot = _resolve_snapshot(root)
    witness = _resolve_witness_status(root)
    sig_tip = _signature_tip(root)
    status_hash = ""
    if integrity.payload:
        from hashlib import sha256

        status_hash = sha256(canonical_json_bytes(integrity.payload)).hexdigest()

    reason_stack = integrity.payload.get("reason_stack") if isinstance(integrity.payload.get("reason_stack"), list) else []
    top_reasons = [str(item) for item in reason_stack[:5]]
    payload: dict[str, Any] = {
        "posture": integrity.payload.get("strategic_posture"),
        "mode": integrity.payload.get("operating_mode"),
        "quarantine": integrity.payload.get("quarantine_active"),
        "pressure": integrity.payload.get("pressure_summary"),
        "integrity_primary_reason": integrity.payload.get("primary_reason"),
        "integrity_reason_stack_top5": top_reasons,
        "allow": {
            "mutation": bool(integrity.payload.get("mutation_allowed")),
            "publish": bool(integrity.payload.get("publish_allowed")),
            "automerge": bool(integrity.payload.get("automerge_allowed")),
        },
        "budget": {
            "remaining": integrity.payload.get("budget_remaining") if isinstance(integrity.payload.get("budget_remaining"), dict) else {},
            "exhausted": bool(integrity.payload.get("budget_exhausted")),
        },
        "snapshot": {
            "present": bool(snapshot.payload),
            "cadence": _snapshot_cadence(root, integrity.payload, snapshot.payload, status_hash),
            "signature_tip": sig_tip,
            "witness_status": witness.payload,
            "policy_hash": snapshot.payload.get("policy_hash"),
            "integrity_status_hash": snapshot.payload.get("integrity_status_hash"),
        },
        "signature_verification": _map_signature_streams(integrity.payload),
        "policy_hash": integrity.payload.get("policy_hash") or snapshot.payload.get("policy_hash"),
        "integrity_status_hash": status_hash or snapshot.payload.get("integrity_status_hash"),
        "artifacts": {
            "integrity_status": {"path": integrity.path, "resolution": integrity.resolution},
            "attestation_snapshot": {"path": snapshot.path, "resolution": snapshot.resolution},
            "witness_status": {"path": witness.path, "resolution": witness.resolution},
            "snapshot_signature_tip": {"path": sig_tip.get("path"), "resolution": "disk"},
        },
    }
    return payload


def _exit_code(payload: dict[str, object]) -> int:
    has_integrity = bool(payload.get("artifacts", {}).get("integrity_status", {}).get("path"))
    has_snapshot = bool(payload.get("artifacts", {}).get("attestation_snapshot", {}).get("path"))
    if not has_integrity and not has_snapshot:
        return 3
    sigs = payload.get("signature_verification")
    any_warn = False
    if isinstance(sigs, dict):
        any_warn = any(isinstance(item, dict) and item.get("status") == "warn" for item in sigs.values())
    if payload.get("allow", {}).get("mutation") is False and payload.get("integrity_primary_reason") not in {None, "integrity_ok"}:
        return 2
    if any_warn:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Forge integrity status summary")
    parser.add_argument("--latest", action="store_true", help="print human summary")
    parser.add_argument("--json", action="store_true", help="print canonical JSON summary")
    args = parser.parse_args(argv)

    if not args.latest and not args.json:
        parser.error("choose --latest or --json")
        return 2

    root = Path.cwd().resolve()
    payload = build_status_payload(root)

    if args.json:
        print(canonical_json_bytes(payload).decode("utf-8"), end="")
    else:
        print(f"posture={payload.get('posture')} mode={payload.get('mode')} quarantine={payload.get('quarantine')} pressure={payload.get('pressure')}")
        print(f"integrity_primary_reason={payload.get('integrity_primary_reason')}")
        print("reason_stack_top5=" + ", ".join(payload.get("integrity_reason_stack_top5", [])))
        allow = payload.get("allow", {})
        print(f"allow mutation={allow.get('mutation')} publish={allow.get('publish')} automerge={allow.get('automerge')}")
        budget = payload.get("budget", {})
        print(f"budget exhausted={budget.get('exhausted')} remaining={budget.get('remaining')}")
        cadence = payload.get("snapshot", {}).get("cadence", {})
        print(f"snapshot present={payload.get('snapshot', {}).get('present')} cadence={cadence}")
        print(f"signature_verification={payload.get('signature_verification')}")
        print(f"policy_hash={payload.get('policy_hash')} integrity_status_hash={payload.get('integrity_status_hash')}")
        print(f"artifacts={payload.get('artifacts')}")
    return _exit_code(payload)


if __name__ == "__main__":
    raise SystemExit(main())
