from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sentientos.audit_chain_gate import verify_audit_chain
from sentientos.audit_recovery import (
    RecoveryCheckpoint,
    append_checkpoint,
    break_fingerprint,
    checkpoint_id_from_payload,
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _report_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_report(repo_root: Path, payload: dict[str, object]) -> Path:
    out = repo_root / "glow/forge/audit_reports" / f"audit_reanchor_{_report_tag()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create explicit audit-chain re-anchor checkpoint")
    parser.add_argument("--reason", required=True, help="operator reason for trust re-anchor")
    parser.add_argument(
        "--continuation-log",
        default="pulse/audit/privileged_audit.runtime.jsonl",
        help="log path expected to continue after checkpoint",
    )
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    verification = verify_audit_chain(root)
    if verification.first_break is None:
        payload = {
            "schema_version": 1,
            "created_at": _iso_now(),
            "status": "refused",
            "reason": "no_break_detected",
            "verification": verification.to_dict(),
        }
        report_path = _write_report(root, payload)
        print(json.dumps({"status": "refused", "report_path": str(report_path.relative_to(root))}, sort_keys=True))
        return 1

    first_break = verification.first_break
    fingerprint = break_fingerprint(
        path=first_break.path,
        line_number=first_break.line_number,
        expected_prev_hash=first_break.expected_prev_hash,
        found_prev_hash=first_break.found_prev_hash,
    )

    created_at = _iso_now()
    payload_for_id = {
        "created_at": created_at,
        "break_fingerprint": fingerprint,
        "trusted_history_head_hash": verification.trusted_history_head_hash or ("0" * 64),
        "continuation_anchor_prev_hash": verification.trusted_history_head_hash or ("0" * 64),
        "continuation_log_path": args.continuation_log,
        "reason": args.reason,
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
        continuation_log_path=args.continuation_log,
        reason=args.reason,
        status="active",
    )
    checkpoint_path = append_checkpoint(root, checkpoint)

    after = verify_audit_chain(root)
    payload = {
        "schema_version": 1,
        "created_at": created_at,
        "status": "checkpoint_created",
        "checkpoint": checkpoint.to_dict(),
        "checkpoint_path": str(checkpoint_path.relative_to(root)),
        "verification_before": verification.to_dict(),
        "verification_after": after.to_dict(),
    }
    report_path = _write_report(root, payload)
    print(
        json.dumps(
            {
                "status": "checkpoint_created",
                "checkpoint_id": checkpoint_id,
                "checkpoint_path": str(checkpoint_path.relative_to(root)),
                "report_path": str(report_path.relative_to(root)),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
