from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Any

from sentientos import artifact_catalog
from sentientos.attestation import append_jsonl, as_str, canonical_json_bytes, compute_envelope_hash, iso_now, read_json, read_jsonl, write_json
from sentientos.attestation_snapshot import SIGNATURE_INDEX_PATH as LOCAL_SNAPSHOT_SIG_INDEX
from sentientos.attestation_snapshot import _resolve_signer as resolve_snapshot_signer
from sentientos.attestation_snapshot import _verify_signature as verify_snapshot_signature
from sentientos.consistency_checks import compare_tick_vs_replay
from sentientos.operator_report_attestation import maybe_sign_operator_report
from sentientos.operator_report_attestation import _resolve_signer as resolve_operator_signer
from sentientos.operator_report_attestation import _verify_signature as verify_operator_signature
from sentientos.remote_bundle import load_bundle, load_manifest, sha256_file, sha256_payload
from sentientos.schema_registry import SchemaName, normalize


def _verify_sig_rows(rows: list[dict[str, object]], *, stream: str) -> dict[str, object]:
    if not rows:
        return {"status": "skipped", "reason": "signature_missing", "checked_n": 0, "last_ok_sig_hash": None}
    prev_hash: str | None = None
    checked_n = 0
    last_ok: str | None = None
    for idx, row in enumerate(rows):
        payload = {
            "schema_version": int(row.get("schema_version") or 1),
            "kind": as_str(row.get("kind")) or "",
            "object_id": as_str(row.get("object_id")) or "",
            "created_at": as_str(row.get("created_at")) or "",
            "path": as_str(row.get("path")) or "",
            "object_sha256": as_str(row.get("object_sha256")) or "",
            "prev_sig_hash": as_str(row.get("prev_sig_hash")),
            "public_key_id": as_str(row.get("public_key_id")) or "",
            "algorithm": as_str(row.get("algorithm")) or "",
        }
        payload_sha = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        if payload_sha != as_str(row.get("sig_payload_sha256")):
            return {"status": "fail", "reason": "sig_payload_sha_mismatch", "checked_n": checked_n, "last_ok_sig_hash": last_ok}
        sig_hash = as_str(row.get("sig_hash"))
        if sig_hash != compute_envelope_hash(dict(row), hash_field="sig_hash"):
            return {"status": "fail", "reason": "sig_hash_mismatch", "checked_n": checked_n, "last_ok_sig_hash": last_ok}
        if idx > 0 and as_str(row.get("prev_sig_hash")) != prev_hash:
            return {"status": "fail", "reason": "prev_sig_hash_mismatch", "checked_n": checked_n, "last_ok_sig_hash": last_ok}

        signature = as_str(row.get("signature")) or ""
        if stream == "attestation_snapshots":
            signer = resolve_snapshot_signer(require_configured=False)
            signature_ok = True if signer is None else verify_snapshot_signature(signer, payload_sha, signature)
        else:
            signer = resolve_operator_signer(require_configured=False)
            signature_ok = True if signer is None else verify_operator_signature(signer, payload_sha, signature)
        if not signature_ok:
            return {"status": "fail", "reason": "signature_invalid", "checked_n": checked_n, "last_ok_sig_hash": last_ok}

        prev_hash = sig_hash
        checked_n += 1
        last_ok = sig_hash
    return {"status": "ok", "reason": "ok", "checked_n": checked_n, "last_ok_sig_hash": last_ok}


def _load_chain_rows(bundle_root: Path, stream_name: str, *, last_n: int) -> list[dict[str, object]]:
    rows = read_jsonl(bundle_root / "signatures" / stream_name / "signatures_index.jsonl")
    return rows[-max(1, last_n) :] if rows else []


def _resolve_local(root: Path, *, kind: str, disk_glob: str) -> dict[str, object]:
    entry = artifact_catalog.latest(root, kind)
    if entry is not None:
        payload = artifact_catalog.load_catalog_artifact(root, entry)
        if payload:
            return payload
    rows = sorted(root.glob(disk_glob), key=lambda item: item.name)
    return read_json(rows[-1]) if rows else {}


def _tip_from_index(path: Path) -> str | None:
    rows = read_jsonl(path)
    if not rows:
        return None
    return as_str(rows[-1].get("sig_hash"))


def _divergence(remote_snapshot: dict[str, object], remote_integrity: dict[str, object], local_snapshot: dict[str, object], local_integrity: dict[str, object], remote_snapshot_tip: str | None, local_snapshot_tip: str | None) -> list[str]:
    ordered: list[tuple[str, bool]] = [
        ("policy_hash_mismatch", as_str(remote_snapshot.get("policy_hash")) != as_str(local_snapshot.get("policy_hash"))),
        ("attestation_snapshot_tip_mismatch", remote_snapshot_tip != local_snapshot_tip),
        ("integrity_status_hash_mismatch", sha256_payload(remote_integrity) != sha256_payload(local_integrity) if remote_integrity and local_integrity else False),
        ("goal_graph_hash_mismatch", as_str(remote_snapshot.get("latest_goal_graph_hash")) != as_str(local_snapshot.get("latest_goal_graph_hash"))),
        ("rollup_signature_tip_mismatch", as_str(remote_snapshot.get("latest_rollup_sig_hash")) != as_str(local_snapshot.get("latest_rollup_sig_hash"))),
        ("strategic_signature_tip_mismatch", as_str(remote_snapshot.get("latest_strategic_sig_hash")) != as_str(local_snapshot.get("latest_strategic_sig_hash"))),
    ]
    return [reason for reason, mismatch in ordered if mismatch]


def run_probe(*, root: Path, bundle_path: Path, last_n: int, write: bool) -> tuple[dict[str, object], int]:
    loaded = load_bundle(bundle_path)
    try:
        manifest = load_manifest(loaded.root)
        if not manifest:
            return ({"error": "manifest_missing"}, 3)
        artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
        if "attestation_snapshot.json" not in artifacts or "integrity_status.json" not in artifacts:
            return ({"error": "missing_critical_artifacts"}, 3)
        tips = manifest.get("signature_stream_tips") if isinstance(manifest.get("signature_stream_tips"), dict) else {}
        remote_snapshot_tip = as_str(tips.get("attestation_snapshots"))

        bundle_hash_status = {"status": "ok", "reason": "ok"}
        for name, meta in artifacts.items():
            if not isinstance(meta, dict):
                continue
            rel = as_str(meta.get("path"))
            expected = as_str(meta.get("sha256"))
            if not rel or not expected or sha256_file(loaded.root / rel) != expected:
                bundle_hash_status = {"status": "fail", "reason": f"artifact_sha256_mismatch:{name}"}
                break

        remote_snapshot = read_json(loaded.root / "artifacts/attestation_snapshot.json")
        remote_integrity = read_json(loaded.root / "artifacts/integrity_status.json")
        remote_replay = read_json(loaded.root / "artifacts/operator_replay_report.json")
        snap_rows = _load_chain_rows(loaded.root, "attestation_snapshots", last_n=last_n)
        op_rows = _load_chain_rows(loaded.root, "operator_reports", last_n=last_n)
        snapshot_verify = _verify_sig_rows(snap_rows, stream="attestation_snapshots")
        operator_verify = _verify_sig_rows(op_rows, stream="operator_reports") if op_rows else {"status": "skipped_missing", "reason": "stream_missing", "checked_n": 0, "last_ok_sig_hash": None}

        consistency_payload = {"status": "skipped_missing", "reason": "replay_or_integrity_missing"}
        if remote_integrity and remote_replay:
            check = compare_tick_vs_replay(remote_integrity | {"integrity_overall": remote_integrity.get("status")}, remote_replay)
            consistency_payload = {"status": check.status, "reason": check.reason}

        local_snapshot = _resolve_local(root, kind="attestation_snapshot", disk_glob="glow/forge/attestation/snapshots/snapshot_*.json")
        local_integrity = _resolve_local(root, kind="integrity_status", disk_glob="glow/forge/integrity/status_*.json")
        local_snapshot_tip = _tip_from_index(root / LOCAL_SNAPSHOT_SIG_INDEX)
        divergence = _divergence(remote_snapshot, remote_integrity, local_snapshot, local_integrity, remote_snapshot_tip, local_snapshot_tip)

        compare_status = "ok"
        if divergence:
            compare_status = "fail" if divergence[0] in {"policy_hash_mismatch", "attestation_snapshot_tip_mismatch"} else "warn"

        report = {
            "schema_version": 1,
            "ts": iso_now(),
            "remote_node_id": manifest.get("node_id") or "unknown",
            "remote_manifest_hash": hashlib.sha256(canonical_json_bytes(manifest)).hexdigest(),
            "remote_policy_hash": remote_snapshot.get("policy_hash"),
            "remote_integrity_status_hash": sha256_payload(remote_integrity) if remote_integrity else None,
            "remote_attestation_snapshot_hash": sha256_payload(remote_snapshot) if remote_snapshot else None,
            "remote_attestation_snapshot_tip": remote_snapshot_tip,
            "remote_operator_reports_tip": as_str((tips or {}).get("operator_reports")) or operator_verify.get("last_ok_sig_hash"),
            "remote_verification": {
                "attestation_snapshot_chain": snapshot_verify,
                "operator_reports_chain": operator_verify,
                "bundle_hashes_ok": bundle_hash_status,
                "remote_tick_vs_replay_consistency": consistency_payload,
            },
            "local_state": {
                "policy_hash": local_snapshot.get("policy_hash"),
                "integrity_status_hash": sha256_payload(local_integrity) if local_integrity else None,
                "attestation_snapshot_hash": sha256_payload(local_snapshot) if local_snapshot else None,
                "attestation_snapshot_tip": local_snapshot_tip,
            },
            "compare_remote_to_local": {
                "status": compare_status,
                "divergence_reasons": divergence,
                "policy_hash_mismatch": "policy_hash_mismatch" in divergence,
                "integrity_status_hash_mismatch": "integrity_status_hash_mismatch" in divergence,
                "snapshot_tip_mismatch": "attestation_snapshot_tip_mismatch" in divergence,
                "goal_graph_hash_mismatch": "goal_graph_hash_mismatch" in divergence,
            },
            "provenance": {
                "probe_input_resolution": loaded.source,
                "paths_used": [str(bundle_path)],
                "exit_code": 0,
            },
        }
        normalized, _warnings = normalize(report, SchemaName.REMOTE_PROBE_REPORT)

        exit_code = 0
        if bundle_hash_status["status"] == "fail" or snapshot_verify["status"] == "fail" or operator_verify["status"] == "fail":
            exit_code = 2
        elif compare_status == "fail":
            exit_code = 2
        elif compare_status == "warn" or operator_verify["status"] == "skipped_missing" or consistency_payload["status"].startswith("skipped"):
            exit_code = 1
        normalized["provenance"]["exit_code"] = exit_code

        if write:
            node_id = str(normalized.get("remote_node_id") or "unknown").replace("/", "_")
            ts = str(normalized.get("ts") or "unknown").replace(":", "-").replace(".", "-")
            rel = Path("glow/forge/remote_probes") / f"probe_{ts}_{node_id}.json"
            write_json(root / rel, normalized)
            if os.getenv("SENTIENTOS_REMOTE_PROBE_SIGNING", "off") in {"ssh", "hmac-test"}:
                maybe_sign_operator_report(root, kind="remote_probe_report", report_rel_path=str(rel), report_payload=normalized)
            append_jsonl(root / "pulse/remote_probes.jsonl", normalized | {"path": str(rel)})
            compare = normalized.get("compare_remote_to_local") if isinstance(normalized.get("compare_remote_to_local"), dict) else {}
            reasons = compare.get("divergence_reasons") if isinstance(compare.get("divergence_reasons"), list) else []
            artifact_catalog.append_catalog_entry(
                root,
                kind="remote_probe_report",
                artifact_id=f"{normalized.get('remote_node_id')}:{normalized.get('ts')}",
                relative_path=str(rel),
                schema_name=SchemaName.REMOTE_PROBE_REPORT,
                schema_version=int(normalized.get("schema_version") or 1),
                links={
                    "remote_node_id": normalized.get("remote_node_id"),
                    "remote_policy_hash": normalized.get("remote_policy_hash"),
                    "remote_integrity_status_hash": normalized.get("remote_integrity_status_hash"),
                    "remote_attestation_tip": normalized.get("remote_attestation_snapshot_tip"),
                    "remote_operator_tip": normalized.get("remote_operator_reports_tip"),
                    "local_attestation_tip": (normalized.get("local_state") if isinstance(normalized.get("local_state"), dict) else {}).get("attestation_snapshot_tip"),
                },
                summary={"status": compare.get("status"), "primary_reason": reasons[0] if reasons else "ok"},
                ts=str(normalized.get("ts") or ""),
            )
        return normalized, exit_code
    finally:
        loaded.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only remote attestation probe")
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--last-n", type=int, default=25)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    report, exit_code = run_probe(root=Path.cwd().resolve(), bundle_path=Path(args.bundle), last_n=max(1, args.last_n), write=args.write)
    if args.json:
        print(canonical_json_bytes(report).decode("utf-8"), end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
