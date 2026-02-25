from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path

from sentientos.attestation import append_jsonl, canonical_json_bytes, iso_now, safe_ts, write_json


@dataclass(frozen=True)
class PolicyFingerprint:
    schema_version: int
    ts: str
    policy: dict[str, object]
    policy_hash: str
    path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "ts": self.ts,
            "policy": self.policy,
            "policy_hash": self.policy_hash,
            "path": self.path,
        }


def build_policy_dict() -> dict[str, object]:
    policy = {
        "posture": {
            "default": os.getenv("SENTIENTOS_STRATEGIC_POSTURE", "balanced"),
            "mode_default": os.getenv("SENTIENTOS_OPERATING_MODE_DEFAULT", "normal"),
            "quarantine_sensitivity": _env_int("SENTIENTOS_QUARANTINE_SENSITIVITY", 1),
        },
        "risk_budget": {
            "allow_override": os.getenv("SENTIENTOS_RISK_BUDGET_OVERRIDE", "0") == "1",
            "strict": os.getenv("SENTIENTOS_RISK_BUDGET_STRICT", "0") == "1",
        },
        "signing": {
            "rollup_mode": os.getenv("SENTIENTOS_ROLLUP_SIGNING", "off"),
            "strategic_mode": os.getenv("SENTIENTOS_STRATEGIC_SIGNING", "off"),
            "snapshot_mode": os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_SIGNING", "off"),
            "rollup_verify": _verify_block("SENTIENTOS_ROLLUP_SIG"),
            "strategic_verify": _verify_block("SENTIENTOS_STRATEGIC_SIG"),
            "snapshot_verify": _verify_block("SENTIENTOS_ATTESTATION_SNAPSHOT"),
            "witness": {
                "rollup_publish": os.getenv("SENTIENTOS_ROLLUP_WITNESS_PUBLISH", "0") == "1",
                "rollup_backend": os.getenv("SENTIENTOS_ROLLUP_WITNESS_BACKEND", "git-tag"),
                "strategic_publish": os.getenv("SENTIENTOS_STRATEGIC_WITNESS_PUBLISH", "0") == "1",
                "strategic_backend": os.getenv("SENTIENTOS_STRATEGIC_WITNESS_BACKEND", "git"),
                "snapshot_publish": os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_WITNESS_PUBLISH", "0") == "1",
                "snapshot_backend": os.getenv("SENTIENTOS_ATTESTATION_SNAPSHOT_WITNESS_BACKEND", "file"),
            },
        },
        "retention": {
            "enabled": os.getenv("SENTIENTOS_RETENTION_ENABLE", "0") == "1",
            "orchestrator_enabled": os.getenv("SENTIENTOS_ORCHESTRATOR_RETENTION", "0") == "1",
            "max_reports": _env_int("SENTIENTOS_RETENTION_MAX_REPORTS", 200),
            "max_receipts": _env_int("SENTIENTOS_RETENTION_MAX_RECEIPTS", 1000),
            "rollup_weeks": _env_int("SENTIENTOS_RETENTION_ROLLUP_WEEKS", 12),
        },
        "auto_remediation": {
            "enabled": os.getenv("SENTIENTOS_ORCHESTRATOR_AUTO_REMEDIATION", "1") == "1",
            "allow_cautious": os.getenv("SENTIENTOS_AUTO_REMEDIATION_ALLOW_CAUTIOUS", "0") == "1",
            "max_attempts": _env_int("SENTIENTOS_AUTO_REMEDIATION_MAX_ATTEMPTS", 2),
        },
        "strategic": {
            "auto_propose": os.getenv("SENTIENTOS_STRATEGIC_AUTO_PROPOSE", "0") == "1",
            "auto_apply": os.getenv("SENTIENTOS_STRATEGIC_AUTO_APPLY", "0") == "1",
            "apply_requires_stable": os.getenv("SENTIENTOS_STRATEGIC_APPLY_REQUIRES_STABLE", "1") == "1",
        },
    }
    return policy


def compute_policy_hash(policy: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(policy)).hexdigest()


def emit_policy_fingerprint(repo_root: Path, *, ts: str | None = None) -> PolicyFingerprint:
    root = repo_root.resolve()
    generated_at = ts or iso_now()
    policy = build_policy_dict()
    policy_hash = compute_policy_hash(policy)
    rel = Path("glow/forge/policy") / f"policy_{safe_ts(generated_at)}.json"
    payload = {
        "schema_version": 1,
        "ts": generated_at,
        "policy": policy,
        "policy_hash": policy_hash,
    }
    write_json(root / rel, payload)
    append_jsonl(root / "pulse/policy.jsonl", payload | {"path": str(rel)})
    return PolicyFingerprint(schema_version=1, ts=generated_at, policy=policy, policy_hash=policy_hash, path=str(rel))


def _verify_block(prefix: str) -> dict[str, object]:
    enable_name = f"{prefix}_VERIFY"
    enabled = os.getenv(enable_name, "0") == "1"
    return {
        "enabled": enabled,
        "last_n": _env_int(f"{prefix}_VERIFY_LAST_N", 25),
        "warn": os.getenv(f"{prefix}_WARN", "0") == "1",
        "enforce": os.getenv(f"{prefix}_ENFORCE", "0") == "1",
    }


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
