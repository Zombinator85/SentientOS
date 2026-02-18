"""Transactional safety primitives for Forge sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any


@dataclass(slots=True)
class ForgeGitOps:
    """Small git operations interface so tests can monkeypatch safely."""

    def run(self, argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)


@dataclass(slots=True)
class TransactionPolicy:
    enabled: bool = True
    regression_rules: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "ci_baseline": {
                "forbid_pass_to_fail": True,
                "forbid_failed_count_increase": True,
                "improvement_min_decrease": 1,
            },
            "contract_drift": {
                "forbid_new_drift": True,
            },
            "forbid_no_progress": True,
        }
    )
    quarantine_on_failure: bool = True
    quarantine_branch_prefix: str = "quarantine/forge"
    keep_failed_worktree: bool = True


@dataclass(slots=True)
class TransactionSnapshot:
    git_sha: str
    ci_baseline: dict[str, Any]
    contract_status_digest: dict[str, Any]
    timestamp: str


@dataclass(slots=True)
class TransactionResult:
    status: str
    regression_detected: bool
    regression_reasons: list[str]
    quarantine_ref: str | None
    rollback_performed: bool
    artifacts: list[str]


CI_BASELINE_PATH = Path("glow/contracts/ci_baseline.json")
CONTRACT_STATUS_PATH = Path("glow/contracts/contract_status.json")


def capture_snapshot(repo_root: Path, session_root: Path, *, git_ops: ForgeGitOps | None = None) -> TransactionSnapshot:
    _ = repo_root
    ops = git_ops or ForgeGitOps()
    git_sha = _git_sha(session_root, ops)
    baseline = _load_json(session_root / CI_BASELINE_PATH)
    status = _load_json(session_root / CONTRACT_STATUS_PATH)
    digest = {
        "has_drift": _has_contract_drift(status),
        "drift_domains": _drift_domains(status),
        "generated_at": status.get("generated_at") if isinstance(status.get("generated_at"), str) else None,
    }
    return TransactionSnapshot(
        git_sha=git_sha,
        ci_baseline={
            "passed": bool(baseline.get("passed", False)),
            "failed_count": int(baseline.get("failed_count", 0)) if isinstance(baseline.get("failed_count"), int) else 0,
        },
        contract_status_digest=digest,
        timestamp=_iso_now(),
    )


def compare_snapshots(
    before: TransactionSnapshot,
    after: TransactionSnapshot,
    *,
    policy: TransactionPolicy | None = None,
) -> tuple[bool, list[str], bool, str]:
    active = policy or TransactionPolicy()
    reasons: list[str] = []
    ci_rules = active.regression_rules.get("ci_baseline", {})
    before_passed = bool(before.ci_baseline.get("passed", False))
    after_passed = bool(after.ci_baseline.get("passed", False))
    before_failed = int(before.ci_baseline.get("failed_count", 0))
    after_failed = int(after.ci_baseline.get("failed_count", 0))

    if ci_rules.get("forbid_pass_to_fail", True) and before_passed and not after_passed:
        reasons.append("ci_baseline_pass_to_fail")
    if ci_rules.get("forbid_failed_count_increase", True) and after_failed > before_failed:
        reasons.append("ci_baseline_failed_count_increase")

    drift_rules = active.regression_rules.get("contract_drift", {})
    before_drift = bool(before.contract_status_digest.get("has_drift", False))
    after_drift = bool(after.contract_status_digest.get("has_drift", False))
    if drift_rules.get("forbid_new_drift", True) and (not before_drift and after_drift):
        reasons.append("contract_drift_appeared")

    decrease = before_failed - after_failed
    threshold = int(ci_rules.get("improvement_min_decrease", 1))
    improved = decrease >= threshold
    improvement_summary = f"ci_baseline_failed_count_delta:{decrease} ({before_failed}->{after_failed})"

    if active.regression_rules.get("forbid_no_progress", True) and not improved and not reasons:
        reasons.append("no_progress")

    return (bool(reasons), reasons, improved, improvement_summary)


def rollback_session(session_root: Path, *, git_ops: ForgeGitOps | None = None) -> bool:
    ops = git_ops or ForgeGitOps()
    first = ops.run(["git", "reset", "--hard", "HEAD"], cwd=session_root)
    second = ops.run(["git", "clean", "-fd"], cwd=session_root)
    return first.returncode == 0 and second.returncode == 0


def quarantine(
    session_root: Path,
    branch_name: str,
    notes_path: Path,
    *,
    git_ops: ForgeGitOps | None = None,
) -> str | None:
    ops = git_ops or ForgeGitOps()
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    ref = f"{branch_name}-{notes_path.stem.split('_')[-1]}"
    write_res = ops.run(["git", "branch", ref], cwd=session_root)
    if write_res.returncode != 0:
        return None
    notes = {
        "created_at": _iso_now(),
        "session_root": str(session_root),
        "quarantine_ref": ref,
    }
    notes_path.write_text(json.dumps(notes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ref


def _git_sha(root: Path, git_ops: ForgeGitOps) -> str:
    result = git_ops.run(["git", "rev-parse", "--verify", "HEAD"], cwd=root)
    return result.stdout.strip() if result.returncode == 0 else ""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _has_contract_drift(status: dict[str, Any]) -> bool:
    contracts = status.get("contracts")
    if not isinstance(contracts, list):
        return False
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        if bool(contract.get("drifted", False)):
            return True
        drift_type = contract.get("drift_type")
        if isinstance(drift_type, str) and drift_type not in {"none", "baseline_missing"}:
            return True
    return False


def _drift_domains(status: dict[str, Any]) -> list[str]:
    contracts = status.get("contracts")
    domains: list[str] = []
    if not isinstance(contracts, list):
        return domains
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        domain = contract.get("domain_name")
        drifted = bool(contract.get("drifted", False))
        drift_type = contract.get("drift_type")
        if not isinstance(domain, str):
            continue
        if drifted or (isinstance(drift_type, str) and drift_type not in {"none", "baseline_missing"}):
            domains.append(domain)
    return sorted(set(domains))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
