from __future__ import annotations

import argparse
from contextlib import contextmanager
from hashlib import sha256
import os
from pathlib import Path
from typing import Any, Iterator

from sentientos import artifact_catalog
from sentientos.attestation import append_jsonl, canonical_json_bytes, iso_now, write_json
from sentientos.attestation_snapshot import AttestationSnapshot, emit_snapshot, should_emit_snapshot, verify_recent_snapshots
from sentientos.integrity_controller import IntegrityBudget, evaluate_integrity
from sentientos.operator_report_attestation import maybe_sign_operator_report
from sentientos.policy_fingerprint import build_policy_dict, compute_policy_hash, emit_policy_fingerprint
from sentientos.schema_registry import SchemaName, normalize
from sentientos.signed_rollups import latest_catalog_checkpoint_hash, verify_signed_rollups
from sentientos.signed_strategic import verify_recent


@contextmanager
def _temp_env(name: str, value: str) -> Iterator[None]:
    prior = os.getenv(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = prior


def _budgeted_verify(root: Path, *, last_n: int) -> dict[str, dict[str, object]]:
    budget = IntegrityBudget.from_env()
    verify_last_n = min(last_n, budget.max_verify_items_per_stream)
    stream_order = ["attestation_snapshot_signatures", "rollup_signatures", "strategic_signatures"]
    priorities = {"attestation_snapshot_signatures": 1, "rollup_signatures": 2, "strategic_signatures": 3}

    active: list[str] = []
    if os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_VERIFY", "0") == "1":
        active.append("attestation_snapshot_signatures")
    if os.getenv("SENTIENTOS_ROLLUP_SIG_VERIFY", "0") == "1":
        active.append("rollup_signatures")
    if os.getenv("SENTIENTOS_STRATEGIC_SIG_VERIFY", "0") == "1":
        active.append("strategic_signatures")

    allowed = set(sorted(active, key=lambda name: priorities[name], reverse=True)[: budget.max_verify_streams_per_tick])
    results: dict[str, dict[str, object]] = {}

    for name in stream_order:
        if name not in active:
            results[name] = {"status": "skipped", "reason": "verify_disabled", "checked_n": 0}
            continue
        if name not in allowed:
            results[name] = {"status": "skipped", "reason": "skipped_budget_exhausted", "checked_n": 0}
            continue
        if name == "attestation_snapshot_signatures":
            check = verify_recent_snapshots(root, last=verify_last_n)
            results[name] = {"status": check.status if check.status else "ok", "reason": check.reason or "ok", "checked_n": check.checked_n}
        elif name == "rollup_signatures":
            ok, reason = verify_signed_rollups(root, last_weeks=verify_last_n)
            if ok:
                results[name] = {"status": "ok", "reason": "ok", "checked_n": verify_last_n}
            else:
                enforce = os.getenv("SENTIENTOS_ROLLUP_SIG_ENFORCE", "0") == "1"
                results[name] = {"status": "fail" if enforce else "warn", "reason": reason or "rollup_signature_verify_failed", "checked_n": 0}
        else:
            check = verify_recent(root, last=verify_last_n)
            if check.ok:
                results[name] = {"status": "ok", "reason": "ok", "checked_n": check.checked_n}
            else:
                enforce = os.getenv("SENTIENTOS_STRATEGIC_SIG_ENFORCE", "0") == "1"
                results[name] = {"status": "fail" if enforce else "warn", "reason": check.reason or "strategic_signature_verify_failed", "checked_n": check.checked_n}

    return results


def _maybe_emit_snapshot(root: Path, *, emit_requested: bool, integrity_payload: dict[str, object], policy_hash: str) -> dict[str, object]:
    if not emit_requested:
        return {"emitted": False, "reason": "flag_disabled", "path": None}
    integrity_hash = sha256(canonical_json_bytes(integrity_payload)).hexdigest()
    now = str(integrity_payload.get("ts") or iso_now())
    min_interval = max(1, int(os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_MIN_INTERVAL_SECONDS", "600")))
    allowed = should_emit_snapshot(
        root,
        ts=now,
        integrity_status_hash=integrity_hash,
        policy_hash=policy_hash,
        goal_graph_hash=None,
        min_interval_seconds=min_interval,
    )
    if not allowed:
        return {"emitted": False, "reason": "cadence_not_elapsed", "path": None}
    snapshot = AttestationSnapshot(
        schema_version=1,
        ts=now,
        policy_hash=policy_hash,
        integrity_status_hash=integrity_hash,
        latest_rollup_sig_hash=None,
        latest_strategic_sig_hash=None,
        latest_goal_graph_hash=None,
        latest_catalog_checkpoint_hash=latest_catalog_checkpoint_hash(root),
        doctrine_bundle_sha256=None,
        witness_summary={"replay_mode": True},
    )
    rel = emit_snapshot(root, snapshot)
    return {"emitted": True, "reason": "emitted", "path": rel}


def _normalize_report(payload: dict[str, Any]) -> dict[str, object]:
    normalized, _warnings = normalize(payload, SchemaName.FORGE_REPLAY_REPORT)
    return normalized


def _overall_from_integrity(integrity_status: str) -> str:
    if integrity_status in {"ok", "warn", "fail"}:
        return integrity_status
    return "missing"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay deterministic Forge integrity verification")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--last-n", type=int, default=25)
    parser.add_argument("--emit-snapshot", type=int, choices=[0, 1], default=0)
    parser.add_argument("--write-policy", type=int, choices=[0, 1], default=0)
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    catalog_path = root / artifact_catalog.CATALOG_PATH
    catalog_status: dict[str, object]
    if catalog_path.exists():
        catalog_status = {"status": "skipped", "reason": "catalog_exists"}
    elif os.getenv("SENTIENTOS_ALLOW_CATALOG_REBUILD", "0") == "1":
        report = artifact_catalog.rebuild_catalog_from_disk(root)
        catalog_status = {"status": "performed", "reason": "catalog_rebuilt", "report_path": report.get("report_path")}
    else:
        catalog_status = {"status": "denied", "reason": "skipped_catalog_rebuild"}

    policy = build_policy_dict()
    policy_hash = compute_policy_hash(policy)
    if args.write_policy == 1:
        emitted = emit_policy_fingerprint(root)
        policy_hash = emitted.policy_hash

    with _temp_env("SENTIENTOS_INTEGRITY_MAX_VERIFY_LAST_N", str(max(1, args.last_n))):
        integrity = evaluate_integrity(root, policy_hash=policy_hash, replay_mode=True)

    verify_results = _budgeted_verify(root, last_n=max(1, args.last_n)) if args.verify else {}
    snapshot_emit = _maybe_emit_snapshot(root, emit_requested=args.emit_snapshot == 1, integrity_payload=integrity.to_dict(), policy_hash=policy_hash)

    ts = iso_now()
    reason_stack = [str(item) for item in integrity.reason_stack[:10]]
    payload = _normalize_report(
        {
            "schema_version": 1,
            "ts": ts,
            "replay_mode": True,
            "inputs": {
                "last_n": max(1, args.last_n),
                "verify_enabled": bool(args.verify),
                "emit_snapshot_requested": bool(args.emit_snapshot),
                "catalog_rebuild_requested": os.getenv("SENTIENTOS_ALLOW_CATALOG_REBUILD", "0") == "1",
            },
            "policy_hash": policy_hash,
            "integrity_status_hash": integrity.canonical_hash(),
            "integrity_overall": _overall_from_integrity(integrity.status),
            "primary_reason": integrity.primary_reason,
            "reason_stack": reason_stack,
            "verification_results": {
                "snapshot": verify_results.get("attestation_snapshot_signatures", {"status": "skipped", "reason": "verify_disabled", "checked_n": 0}),
                "rollup": verify_results.get("rollup_signatures", {"status": "skipped", "reason": "verify_disabled", "checked_n": 0}),
                "strategic": verify_results.get("strategic_signatures", {"status": "skipped", "reason": "verify_disabled", "checked_n": 0}),
            },
            "snapshot_emitted": bool(snapshot_emit.get("emitted")),
            "snapshot_emit_reason": snapshot_emit.get("reason"),
            "catalog_rebuild": {"status": catalog_status.get("status"), "reason": catalog_status.get("reason")},
            "provenance": {
                "integrity_status": {"path": None, "resolution_source": "disk"},
                "snapshot": {"path": snapshot_emit.get("path"), "resolution_source": "disk"},
                "catalog_report_path": catalog_status.get("report_path"),
            },
            "exit_code": 0,
        }
    )
    out_rel = Path("glow/forge/replay") / f"replay_{ts.replace(':', '-').replace('.', '-')}.json"
    write_json(root / out_rel, payload)

    sign = maybe_sign_operator_report(root, kind="operator_replay", report_rel_path=str(out_rel), report_payload=payload)
    if sign:
        payload["operator_signature_hash"] = sign.get("sig_hash")
        write_json(root / out_rel, payload)

    artifact_catalog.append_catalog_entry(
        root,
        kind="operator_replay",
        artifact_id=str(payload.get("ts") or out_rel.name),
        relative_path=str(out_rel),
        schema_name=SchemaName.FORGE_REPLAY_REPORT,
        schema_version=int(payload.get("schema_version") or 1),
        links={
            "policy_hash": payload.get("policy_hash"),
            "integrity_status_hash": payload.get("integrity_status_hash"),
            "attestation_snapshot_tip": payload.get("ts") if payload.get("snapshot_emitted") else None,
            "attestation_snapshot_hash": payload.get("integrity_status_hash") if payload.get("snapshot_emitted") else None,
        },
        summary={
            "status": payload.get("integrity_overall"),
            "primary_reason": payload.get("primary_reason"),
        },
        ts=str(payload.get("ts") or ts),
    )

    append_jsonl(
        root / "pulse/replay_runs.jsonl",
        {
            "ts": ts,
            "path": str(out_rel),
            "integrity_status": payload.get("integrity_overall"),
            "policy_hash": payload.get("policy_hash"),
            "integrity_status_hash": payload.get("integrity_status_hash"),
            "exit_code": payload.get("exit_code"),
        },
    )
    print(canonical_json_bytes(payload).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
