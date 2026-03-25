from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from sentientos.attestation import iso_now, read_json, write_json
from sentientos.audit_chain_gate import AuditChainVerification

StrictAuditBucket = Literal[
    "healthy_strict",
    "healthy_reanchored",
    "broken_preserved_nonblocking",
    "degraded_runtime_split",
    "blocking_chain_break",
    "missing_required_audit_artifacts",
    "indeterminate_audit_state",
]

STRICT_BLOCKING_BUCKETS = {"blocking_chain_break", "missing_required_audit_artifacts"}
STRICT_DEGRADED_BUCKETS = {"degraded_runtime_split", "indeterminate_audit_state"}
STRICT_ACCEPTABLE_BUCKETS = {"healthy_strict", "healthy_reanchored", "broken_preserved_nonblocking"}


@dataclass(frozen=True)
class StrictAuditInputs:
    baseline_path: str
    runtime_path: str
    baseline_status: str
    runtime_status: str
    baseline_errors: list[str]
    runtime_errors: list[str]
    runtime_error_kind: str
    runtime_error_examples: list[str]
    suggested_fix: str
    environment_issues: list[str]


def _stable_digest(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _bucket_blocking(bucket: StrictAuditBucket) -> bool:
    return bucket in STRICT_BLOCKING_BUCKETS


def _bucket_degraded(bucket: StrictAuditBucket) -> bool:
    return bucket in STRICT_DEGRADED_BUCKETS


def classify_strict_audit_state(*, inputs: StrictAuditInputs, audit_chain: AuditChainVerification) -> tuple[StrictAuditBucket, list[str], str]:
    reasons: list[str] = []

    baseline_missing = not Path(inputs.baseline_path).exists()
    runtime_missing = not Path(inputs.runtime_path).exists()
    if baseline_missing:
        reasons.append(f"baseline_missing:{inputs.baseline_path}")
    if runtime_missing:
        reasons.append(f"runtime_missing:{inputs.runtime_path}")
    if baseline_missing or runtime_missing:
        return "missing_required_audit_artifacts", reasons, "blocking"

    if inputs.environment_issues:
        reasons.extend(f"environment:{item}" for item in inputs.environment_issues)
        return "indeterminate_audit_state", reasons, "degraded"

    recovery = audit_chain.recovery_state or {}
    history_state = str(recovery.get("history_state") or "unknown")
    continuation_descends = bool(recovery.get("continuation_descends_from_anchor") is True)
    checkpoint_id = recovery.get("checkpoint_id")

    if audit_chain.status == "ok":
        if inputs.baseline_status == "ok" and inputs.runtime_status == "ok":
            reasons.append("audit_chain_ok")
            return "healthy_strict", reasons, "acceptable"
        reasons.append(f"runtime_or_baseline_degraded baseline={inputs.baseline_status} runtime={inputs.runtime_status}")
        return "degraded_runtime_split", reasons, "degraded"

    if audit_chain.status == "reanchored":
        if continuation_descends and inputs.runtime_status == "ok":
            reasons.append("reanchor_checkpoint_with_trusted_continuation")
            return "healthy_reanchored", reasons, "acceptable"
        reasons.append("reanchor_present_but_runtime_continuation_untrusted")
        return "degraded_runtime_split", reasons, "degraded"

    if history_state == "broken_preserved" and checkpoint_id:
        if inputs.runtime_status == "ok":
            reasons.append("checkpoint_present_history_preserved_runtime_ok")
            return "broken_preserved_nonblocking", reasons, "acceptable"
        reasons.append("checkpoint_present_but_runtime_split")
        return "degraded_runtime_split", reasons, "degraded"

    reasons.append(f"audit_chain_unresolved status={audit_chain.status} history_state={history_state}")
    return "blocking_chain_break", reasons, "blocking"


def write_strict_audit_artifacts(
    repo_root: Path,
    *,
    inputs: StrictAuditInputs,
    audit_chain: AuditChainVerification,
    verify_result: dict[str, Any] | None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    out_root = root / "glow" / "contracts"
    out_root.mkdir(parents=True, exist_ok=True)

    generated_at = iso_now()
    bucket, reasons, readiness = classify_strict_audit_state(inputs=inputs, audit_chain=audit_chain)

    status_payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "bucket": bucket,
        "readiness_class": readiness,
        "blocking": _bucket_blocking(bucket),
        "degraded": _bucket_degraded(bucket),
        "acceptable_under_preserved_history": bucket in STRICT_ACCEPTABLE_BUCKETS,
        "preserved_history_visible": bool((audit_chain.recovery_state or {}).get("history_state") in {"broken_preserved", "reanchored_continuation"}),
        "checkpoint_present": bool((audit_chain.recovery_state or {}).get("checkpoint_id")),
        "continuation_descends_from_anchor": (audit_chain.recovery_state or {}).get("continuation_descends_from_anchor"),
        "status_hint": reasons[0] if reasons else "none",
    }

    breakdown_payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "bucket": bucket,
        "classification_reasons": reasons,
        "strict_probe": {
            "baseline_status": inputs.baseline_status,
            "runtime_status": inputs.runtime_status,
            "baseline_path": inputs.baseline_path,
            "runtime_path": inputs.runtime_path,
            "runtime_error_kind": inputs.runtime_error_kind,
            "runtime_error_examples": inputs.runtime_error_examples[:10],
            "baseline_error_count": len(inputs.baseline_errors),
            "runtime_error_count": len(inputs.runtime_errors),
            "suggested_fix": inputs.suggested_fix,
            "environment_issues": inputs.environment_issues,
        },
        "audit_chain": audit_chain.to_dict(),
    }

    recovery_links = {
        "schema_version": 1,
        "generated_at": generated_at,
        "links": {
            "baseline_log": inputs.baseline_path,
            "runtime_log": inputs.runtime_path,
            "audit_chain_report": "glow/forge/audit_reports/latest.json",
            "audit_chain_checkpoint_ledger": "glow/forge/audit_reports/audit_recovery_checkpoints.jsonl",
            "verify_audits_result": "glow/audits/verify_audits_result.json",
            "strict_status": "glow/contracts/strict_audit_status.json",
            "strict_breakdown": "glow/contracts/strict_audit_breakdown.json",
            "strict_manifest": "glow/contracts/strict_audit_manifest.json",
        },
        "responsible_chain_state": {
            "audit_chain_status": audit_chain.status,
            "history_state": (audit_chain.recovery_state or {}).get("history_state"),
            "checkpoint_id": (audit_chain.recovery_state or {}).get("checkpoint_id"),
            "break_count": audit_chain.break_count,
        },
        "next_artifact_to_inspect": (
            "glow/contracts/strict_audit_breakdown.json"
            if bucket in STRICT_DEGRADED_BUCKETS
            else "glow/forge/audit_reports/latest.json"
            if bucket in STRICT_BLOCKING_BUCKETS
            else "glow/contracts/strict_audit_status.json"
        ),
    }

    manifest_payload = {
        "schema_version": 1,
        "suite": "strict_audit_status_model",
        "generated_at": generated_at,
        "bucket": bucket,
        "readiness_class": readiness,
        "artifacts": {
            "strict_audit_status": "glow/contracts/strict_audit_status.json",
            "strict_audit_breakdown": "glow/contracts/strict_audit_breakdown.json",
            "strict_audit_recovery_links": "glow/contracts/strict_audit_recovery_links.json",
            "strict_audit_manifest": "glow/contracts/strict_audit_manifest.json",
            "final_strict_audit_digest": "glow/contracts/final_strict_audit_digest.json",
        },
        "inputs": {
            "baseline_log": inputs.baseline_path,
            "runtime_log": inputs.runtime_path,
            "audit_chain_report": "glow/forge/audit_reports/latest.json",
            "verify_audits_result": "glow/audits/verify_audits_result.json",
        },
    }

    if isinstance(verify_result, dict):
        manifest_payload["verify_result"] = {
            "status": verify_result.get("status"),
            "reason": verify_result.get("reason"),
            "exit_code": verify_result.get("exit_code"),
        }

    digest_payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "strict_audit_status_digest": _stable_digest(status_payload),
        "strict_audit_breakdown_digest": _stable_digest(breakdown_payload),
        "strict_audit_recovery_links_digest": _stable_digest(recovery_links),
        "strict_audit_manifest_digest": _stable_digest(manifest_payload),
    }
    digest_payload["strict_audit_digest"] = _stable_digest(digest_payload)

    write_json(out_root / "strict_audit_status.json", status_payload)
    write_json(out_root / "strict_audit_breakdown.json", breakdown_payload)
    write_json(out_root / "strict_audit_recovery_links.json", recovery_links)
    write_json(out_root / "strict_audit_manifest.json", manifest_payload)
    write_json(out_root / "final_strict_audit_digest.json", digest_payload)

    return {
        "bucket": bucket,
        "readiness_class": readiness,
        "blocking": status_payload["blocking"],
        "degraded": status_payload["degraded"],
        "artifact_paths": manifest_payload["artifacts"],
    }


def load_strict_audit_status(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    return cast(dict[str, Any], read_json(root / "glow/contracts/strict_audit_status.json"))
