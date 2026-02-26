from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from typing import Any

from sentientos import artifact_catalog
from sentientos.attestation import canonical_json_bytes, read_json, read_jsonl, write_json
from sentientos.attestation_snapshot import SIGNATURE_INDEX_PATH, SNAPSHOT_DIR, SNAPSHOT_PULSE_PATH, should_emit_snapshot
from sentientos.consistency_checks import compare_tick_vs_replay, replay_is_recent
from sentientos.operator_report_attestation import maybe_sign_operator_report, operator_signing_status, verify_recent_operator_reports
from sentientos.schema_registry import SchemaName, normalize


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


def _resolve_replay(root: Path) -> ResolvedArtifact:
    return _resolve_catalog_then_disk(root, kind="operator_replay", disk_glob="glow/forge/replay/replay_*.json")


def _signature_tip(root: Path) -> dict[str, object]:
    rows = read_jsonl(root / SIGNATURE_INDEX_PATH)
    if not rows:
        return {"sig_hash": None, "path": str(SIGNATURE_INDEX_PATH), "status": "missing"}
    latest = rows[-1]
    sig_hash = latest.get("sig_hash") if isinstance(latest.get("sig_hash"), str) else None
    return {"sig_hash": sig_hash, "path": str(SIGNATURE_INDEX_PATH), "status": "present"}


def _map_signature_streams(integrity: dict[str, object]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
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
        out[key] = {"status": status, "reason": reason, "checked_n": 0}
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


def _overall(status_value: object) -> str:
    return str(status_value) if str(status_value) in {"ok", "warn", "fail"} else "missing"


def build_status_payload(root: Path) -> dict[str, object]:
    integrity = _resolve_integrity(root)
    snapshot = _resolve_snapshot(root)
    witness = _resolve_witness_status(root)
    replay = _resolve_replay(root)
    sig_tip = _signature_tip(root)
    status_hash = sha256(canonical_json_bytes(integrity.payload)).hexdigest() if integrity.payload else ""

    reason_stack = integrity.payload.get("reason_stack") if isinstance(integrity.payload.get("reason_stack"), list) else []
    verify = _map_signature_streams(integrity.payload)

    replay_consistency_status = "unknown"
    replay_consistency_reason = "replay_missing_or_stale"
    if replay.payload and replay_is_recent(replay.payload):
        check = compare_tick_vs_replay(
            {
                "policy_hash": integrity.payload.get("policy_hash") or snapshot.payload.get("policy_hash"),
                "integrity_status_hash": status_hash or snapshot.payload.get("integrity_status_hash"),
                "integrity_overall": _overall(integrity.payload.get("status") or integrity.payload.get("integrity_overall") or "ok"),
                "path": integrity.path,
            },
            replay.payload,
        )
        replay_consistency_status = check.status
        replay_consistency_reason = check.reason

    payload: dict[str, Any] = {
        "schema_version": 1,
        "ts": str(integrity.payload.get("ts") or snapshot.payload.get("ts") or ""),
        "policy_hash": integrity.payload.get("policy_hash") or snapshot.payload.get("policy_hash"),
        "integrity_status_hash": status_hash or snapshot.payload.get("integrity_status_hash"),
        "integrity_overall": _overall(integrity.payload.get("status") or "ok"),
        "primary_reason": integrity.payload.get("primary_reason") or "unknown",
        "reason_stack": [str(item) for item in reason_stack[:10]],
        "mutation_allowed": bool(integrity.payload.get("mutation_allowed")),
        "publish_allowed": bool(integrity.payload.get("publish_allowed")),
        "automerge_allowed": bool(integrity.payload.get("automerge_allowed")),
        "budget_exhausted": bool(integrity.payload.get("budget_exhausted")),
        "budget_remaining": integrity.payload.get("budget_remaining") if isinstance(integrity.payload.get("budget_remaining"), dict) else {},
        "attestation_snapshot_tip": snapshot.payload.get("ts"),
        "attestation_snapshot_hash": snapshot.payload.get("integrity_status_hash"),
        "attestation_snapshot_present": bool(snapshot.payload),
        "verify_summaries": verify,
        "provenance": {
            "integrity_status": {"path": integrity.path, "resolution_source": integrity.resolution},
            "attestation_snapshot": {"path": snapshot.path, "resolution_source": snapshot.resolution},
            "witness_status": {"path": witness.path, "resolution_source": witness.resolution},
        },
        "snapshot": {
            "present": bool(snapshot.payload),
            "cadence": _snapshot_cadence(root, integrity.payload, snapshot.payload, status_hash),
            "signature_tip": sig_tip,
            "witness_status": witness.payload,
        },
        "operator_report_signing": operator_signing_status(root),
        "tick_replay_consistency": replay_consistency_status,
        "tick_replay_consistency_reason": replay_consistency_reason,
        "exit_code": 0,
    }
    normalized, _warnings = normalize(payload, SchemaName.FORGE_STATUS_REPORT)
    return normalized


def _exit_code(payload: dict[str, object]) -> int:
    has_integrity = bool(payload.get("provenance", {}).get("integrity_status", {}).get("path"))
    has_snapshot = bool(payload.get("provenance", {}).get("attestation_snapshot", {}).get("path"))
    if not has_integrity and not has_snapshot:
        return 3
    sigs = payload.get("verify_summaries")
    any_warn = False
    if isinstance(sigs, dict):
        any_warn = any(isinstance(item, dict) and item.get("status") == "warn" for item in sigs.values())
    if payload.get("mutation_allowed") is False and payload.get("primary_reason") not in {None, "integrity_ok"}:
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
    payload["exit_code"] = _exit_code(payload)

    if args.json:
        ts = str(payload.get("ts") or "unknown")
        out_rel = Path("glow/forge/operator/status") / f"status_{ts.replace(':', '-').replace('.', '-')}.json"
        write_json(root / out_rel, payload)
        signature = maybe_sign_operator_report(root, kind="operator_status", report_rel_path=str(out_rel), report_payload=payload)
        if signature:
            payload["operator_signature_hash"] = signature.get("sig_hash")
            verify_result = verify_recent_operator_reports(root, last=1)
            payload["operator_report_signing"]["verify_status"] = verify_result.status
            write_json(root / out_rel, payload)
        artifact_catalog.append_catalog_entry(
            root,
            kind="operator_status",
            artifact_id=str(payload.get("ts") or out_rel.name),
            relative_path=str(out_rel),
            schema_name=SchemaName.FORGE_STATUS_REPORT,
            schema_version=int(payload.get("schema_version") or 1),
            links={
                "policy_hash": payload.get("policy_hash"),
                "integrity_status_hash": payload.get("integrity_status_hash"),
                "attestation_snapshot_tip": payload.get("attestation_snapshot_tip"),
                "attestation_snapshot_hash": payload.get("attestation_snapshot_hash"),
            },
            summary={
                "status": payload.get("integrity_overall"),
                "primary_reason": payload.get("primary_reason"),
            },
            ts=str(payload.get("ts") or ""),
        )
        print(canonical_json_bytes(payload).decode("utf-8"), end="")
    else:
        print(
            f"integrity={payload.get('integrity_overall')} reason={payload.get('primary_reason')} "
            f"mutation={payload.get('mutation_allowed')} publish={payload.get('publish_allowed')} automerge={payload.get('automerge_allowed')}"
        )
        print(f"budget exhausted={payload.get('budget_exhausted')} remaining={payload.get('budget_remaining')}")
        print(f"policy_hash={payload.get('policy_hash')} integrity_status_hash={payload.get('integrity_status_hash')}")
        print(f"signing={payload.get('operator_report_signing')}")
        print(
            "tick_replay_consistency="
            f"{payload.get('tick_replay_consistency')} reason={payload.get('tick_replay_consistency_reason')}"
        )
    return int(payload["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
