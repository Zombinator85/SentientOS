from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sentientos.audit_chain_gate import verify_audit_chain
from sentientos.audit_recovery import (
    RecoveryCheckpoint,
    append_checkpoint,
    break_fingerprint,
    checkpoint_id_from_payload,
    first_continuation_entry,
    load_checkpoints,
)
from sentientos.audit_trust_runtime import evaluate_audit_trust, write_audit_trust_artifacts
from sentientos.federated_governance import get_controller, reset_controller
from sentientos.pulse_trust_epoch import get_manager as get_epoch_manager
from sentientos.pulse_trust_epoch import reset_manager as reset_epoch_manager
from sentientos.runtime_governor import get_runtime_governor, reset_runtime_governor
from sentientos.system_constitution import compose_system_constitution, write_constitution_artifacts
from sentientos.trust_ledger import get_trust_ledger, reset_trust_ledger


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _report_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _set_bootstrap_env(repo_root: Path) -> dict[str, str | None]:
    updates = {
        "SENTIENTOS_REPO_ROOT": str(repo_root),
        "SENTIENTOS_GOVERNOR_ROOT": "glow/governor",
        "SENTIENTOS_FEDERATION_ROOT": "glow/federation",
        "PULSE_TRUST_EPOCH_STATE": "glow/pulse_trust/epoch_state.json",
        "SENTIENTOS_IMMUTABLE_MANIFEST": "vow/immutable_manifest.json",
        "SENTIENTOS_INVARIANTS_PATH": "vow/invariants.yaml",
        "SENTIENTOS_GOVERNOR_CPU": "0.0",
        "SENTIENTOS_GOVERNOR_IO": "0.0",
        "SENTIENTOS_GOVERNOR_THERMAL": "0.0",
        "SENTIENTOS_GOVERNOR_GPU": "0.0",
    }
    previous: dict[str, str | None] = {}
    for key, value in updates.items():
        previous[key] = os.getenv(key)
        os.environ[key] = value
    return previous


def _restore_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _checkpoint_exists(repo_root: Path, fingerprint: str) -> bool:
    return any(item.break_fingerprint == fingerprint and item.status == "active" for item in load_checkpoints(repo_root))


def _maybe_create_checkpoint(repo_root: Path, *, reason: str) -> dict[str, object]:
    verification = verify_audit_chain(repo_root)
    if verification.first_break is None:
        return {"status": "skipped", "reason": "no_break_detected"}

    first_break = verification.first_break
    fingerprint = break_fingerprint(
        path=first_break.path,
        line_number=first_break.line_number,
        expected_prev_hash=first_break.expected_prev_hash,
        found_prev_hash=first_break.found_prev_hash,
    )
    if _checkpoint_exists(repo_root, fingerprint):
        return {"status": "skipped", "reason": "checkpoint_already_present", "break_fingerprint": fingerprint}

    created_at = _iso_now()
    payload_for_id = {
        "created_at": created_at,
        "break_fingerprint": fingerprint,
        "trusted_history_head_hash": verification.trusted_history_head_hash or ("0" * 64),
        "continuation_anchor_prev_hash": verification.trusted_history_head_hash or ("0" * 64),
        "continuation_log_path": "pulse/audit/privileged_audit.runtime.jsonl",
        "reason": reason,
        "break_path": first_break.path,
        "break_line": first_break.line_number,
        "expected_prev_hash": first_break.expected_prev_hash,
        "found_prev_hash": first_break.found_prev_hash,
    }
    checkpoint_id = checkpoint_id_from_payload(payload_for_id)
    checkpoint = RecoveryCheckpoint(
        checkpoint_id=checkpoint_id,
        created_at=created_at,
        break_fingerprint=fingerprint,
        break_path=first_break.path,
        break_line=first_break.line_number,
        expected_prev_hash=first_break.expected_prev_hash,
        found_prev_hash=first_break.found_prev_hash,
        trusted_history_head_hash=str(verification.trusted_history_head_hash or ("0" * 64)),
        continuation_anchor_prev_hash=str(verification.trusted_history_head_hash or ("0" * 64)),
        continuation_log_path="pulse/audit/privileged_audit.runtime.jsonl",
        reason=reason,
        status="active",
    )
    path = append_checkpoint(repo_root, checkpoint)
    return {
        "status": "created",
        "checkpoint_id": checkpoint_id,
        "path": str(path.relative_to(repo_root)),
        "break_fingerprint": fingerprint,
    }


def _hash_entry(timestamp: str, data: object, prev_hash: str) -> str:
    digest = hashlib.sha256()
    digest.update(timestamp.encode("utf-8"))
    digest.update(json.dumps(data, sort_keys=True).encode("utf-8"))
    digest.update(prev_hash.encode("utf-8"))
    return digest.hexdigest()


def _latest_active_checkpoint_for_break(repo_root: Path, break_fingerprint_value: str) -> RecoveryCheckpoint | None:
    candidates = [
        item
        for item in load_checkpoints(repo_root)
        if item.status == "active" and item.break_fingerprint == break_fingerprint_value
    ]
    candidates.sort(key=lambda item: item.created_at)
    return candidates[-1] if candidates else None


def _ensure_continuation_descent(repo_root: Path, checkpoint: RecoveryCheckpoint, *, reason: str) -> dict[str, object]:
    existing = first_continuation_entry(repo_root, checkpoint.continuation_log_path)
    if isinstance(existing, dict) and str(existing.get("prev_hash", "")) == checkpoint.continuation_anchor_prev_hash:
        return {
            "status": "already_descending",
            "continuation_log_path": checkpoint.continuation_log_path,
        }

    timestamp = _iso_now()
    continuation_data = {
        "event": "reanchor_continuation_started",
        "checkpoint_id": checkpoint.checkpoint_id,
        "reason": reason,
        "actor": "bootstrap_trust_restore",
    }
    row = {
        "timestamp": timestamp,
        "data": continuation_data,
        "prev_hash": checkpoint.continuation_anchor_prev_hash,
        "rolling_hash": _hash_entry(timestamp, continuation_data, checkpoint.continuation_anchor_prev_hash),
    }
    continuation_path = repo_root / checkpoint.continuation_log_path
    continuation_path.parent.mkdir(parents=True, exist_ok=True)
    with continuation_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return {
        "status": "appended",
        "continuation_log_path": checkpoint.continuation_log_path,
        "checkpoint_id": checkpoint.checkpoint_id,
    }


def run_bootstrap(repo_root: Path, *, reason: str, create_checkpoint: bool) -> dict[str, object]:
    previous_env = _set_bootstrap_env(repo_root)
    try:
        reset_runtime_governor()
        reset_controller()
        reset_trust_ledger()
        reset_epoch_manager()

        artifacts: list[dict[str, object]] = []
        required = [
            repo_root / "glow/runtime/audit_trust_state.json",
            repo_root / "glow/governor/rollup.json",
            repo_root / "glow/pulse_trust/epoch_state.json",
            repo_root / "glow/federation/governance_digest.json",
            repo_root / "glow/federation/trust_ledger_state.json",
        ]
        before = {str(path.relative_to(repo_root)): path.exists() for path in required}

        epoch_state = get_epoch_manager().load_state()
        artifacts.append({
            "artifact": "pulse_trust_epoch",
            "path": "glow/pulse_trust/epoch_state.json",
            "source": "pulse_trust_epoch.bootstrap_state",
            "active_epoch_id": epoch_state.get("active_epoch_id"),
        })

        governance_digest = get_controller().local_governance_digest().to_dict()
        artifacts.append({
            "artifact": "federation_governance_digest",
            "path": "glow/federation/governance_digest.json",
            "source": "federated_governance.local_governance_digest",
            "digest": governance_digest.get("digest"),
        })

        ledger_schedule = get_trust_ledger().build_probe_schedule(
            peer_ids=[],
            pressure_composite=0.0,
            scheduling_window_open=True,
            storm_active=False,
        )
        artifacts.append({
            "artifact": "trust_ledger_state",
            "path": "glow/federation/trust_ledger_state.json",
            "source": "trust_ledger.build_probe_schedule",
            "pending_actions": len(ledger_schedule.get("pending_actions", [])) if isinstance(ledger_schedule.get("pending_actions"), list) else 0,
        })

        governor_decision = get_runtime_governor().admit_action(
            "control_plane_task",
            actor="bootstrap_trust_restore",
            correlation_id="bootstrap-trust-restore",
            metadata={"subject": "bootstrap_trust_restore", "scope": "local", "task_name": "bootstrap_trust_restore"},
        )
        artifacts.append({
            "artifact": "governor_rollup",
            "path": "glow/governor/rollup.json",
            "source": "runtime_governor.admit_action",
            "decision": governor_decision.reason,
            "allowed": governor_decision.allowed,
        })

        checkpoint_result: dict[str, object] = {"status": "skipped", "reason": "not_requested"}
        if create_checkpoint:
            checkpoint_result = _maybe_create_checkpoint(repo_root, reason=reason)

        continuation_result: dict[str, object] = {"status": "skipped", "reason": "checkpoint_not_available"}
        chain_after_checkpoint = verify_audit_chain(repo_root)
        first_break = chain_after_checkpoint.first_break
        if first_break is not None:
            fingerprint = break_fingerprint(
                path=first_break.path,
                line_number=first_break.line_number,
                expected_prev_hash=first_break.expected_prev_hash,
                found_prev_hash=first_break.found_prev_hash,
            )
            checkpoint = _latest_active_checkpoint_for_break(repo_root, fingerprint)
            if checkpoint is not None:
                continuation_result = _ensure_continuation_descent(repo_root, checkpoint, reason=reason)

        audit_state = evaluate_audit_trust(repo_root, context="bootstrap_trust_restore")
        trust_paths = write_audit_trust_artifacts(repo_root, audit_state, actor="bootstrap_trust_restore")
        artifacts.append({"artifact": "audit_trust_state", "path": trust_paths["snapshot"], "source": "verify_audit_chain"})

        constitution_payload = compose_system_constitution(repo_root)
        constitution_paths = write_constitution_artifacts(repo_root, payload=constitution_payload)

        after = {str(path.relative_to(repo_root)): path.exists() for path in required}
        restored = sorted(path for path, exists in after.items() if exists and not before[path])
        still_missing = sorted(path for path, exists in after.items() if not exists)

        report = {
            "schema_version": 1,
            "created_at": _iso_now(),
            "reason": reason,
            "artifacts_before": before,
            "artifacts_after": after,
            "bootstrapped_artifacts": restored,
            "still_missing_artifacts": still_missing,
            "provenance": artifacts,
            "checkpoint": checkpoint_result,
            "continuation": continuation_result,
            "constitution": {
                "state": constitution_payload.get("constitution_state"),
                "missing_required_artifacts": constitution_payload.get("missing_required_artifacts", []),
                "paths": constitution_paths,
            },
            "audit_chain_after": verify_audit_chain(repo_root).to_dict(),
        }
        out = repo_root / "glow/forge/restoration" / f"trust_restoration_{_report_tag()}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report["report_path"] = str(out.relative_to(repo_root))
        return report
    finally:
        _restore_env(previous_env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic bootstrap + trust restoration for missing constitutional artifacts")
    parser.add_argument("--reason", default="operator_bootstrap_restore", help="operator reason recorded in re-anchor checkpoint")
    parser.add_argument("--no-checkpoint", action="store_true", help="skip explicit audit-chain checkpoint creation")
    parser.add_argument("--json", action="store_true", help="print canonical JSON output")
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    payload = run_bootstrap(root, reason=str(args.reason), create_checkpoint=not args.no_checkpoint)
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"restore_report={payload.get('report_path')} constitution_state={payload.get('constitution', {}).get('state')}")
    still_missing = payload.get("still_missing_artifacts")
    return 1 if isinstance(still_missing, list) and still_missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
