from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json

KNOWN_AUDIT_PATH = "pulse/audit/privileged_audit.runtime.jsonl"

@dataclass(frozen=True)
class CodexStrictAuditRepairPolicy:
    known_runtime_audit_path: str = KNOWN_AUDIT_PATH
    strict_verify_command: str = "python verify_audits.py --strict"
    immutability_verify_command: str = "python scripts/audit_immutability_verifier.py"
    reseal_command: str = "python scripts/audit_chain_reanchor.py --reason codex_strict_runtime_reseal --continuation-log pulse/audit/privileged_audit.runtime.jsonl"

@dataclass(frozen=True)
class CodexStrictAuditRepairRequest:
    strict_output_text: str
    strict_exit_code: int
    audit_path: str = KNOWN_AUDIT_PATH

@dataclass(frozen=True)
class CodexStrictAuditRepairFinding:
    status: str
    classification: str
    reason: str

@dataclass(frozen=True)
class CodexStrictAuditRepairAction:
    commands: tuple[str, ...]
    requires_explicit_opt_in: bool

@dataclass(frozen=True)
class CodexStrictAuditRepairReport:
    finding: CodexStrictAuditRepairFinding
    action: CodexStrictAuditRepairAction
    changed_files: tuple[str, ...] = ()

@dataclass(frozen=True)
class CodexStrictAuditRepairResult:
    policy: CodexStrictAuditRepairPolicy
    report: CodexStrictAuditRepairReport
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _contains_chain_break(text: str, audit_path: str) -> bool:
    low = text.lower()
    return audit_path in text and ("chain" in low and ("break" in low or "mismatch" in low or "failed" in low))


def diagnose_strict_audit_repair(request: CodexStrictAuditRepairRequest, policy: CodexStrictAuditRepairPolicy | None = None) -> CodexStrictAuditRepairResult:
    pol = policy or CodexStrictAuditRepairPolicy()
    if request.strict_exit_code == 0:
        finding = CodexStrictAuditRepairFinding("audit_repair_not_needed", "generated_runtime_artifact_drift", "strict_audits_passed")
        action = CodexStrictAuditRepairAction((pol.strict_verify_command, pol.immutability_verify_command), False)
    elif _contains_chain_break(request.strict_output_text, request.audit_path):
        finding = CodexStrictAuditRepairFinding("audit_repair_ready", "generated_runtime_artifact_drift", "known_runtime_chain_break")
        action = CodexStrictAuditRepairAction((pol.reseal_command, pol.strict_verify_command, pol.immutability_verify_command), True)
    elif "policy" in request.strict_output_text.lower() or "provenance" in request.strict_output_text.lower():
        finding = CodexStrictAuditRepairFinding("audit_repair_requires_manual_review", "task_caused_code_audit_failure", "policy_or_provenance_failure")
        action = CodexStrictAuditRepairAction((pol.strict_verify_command,), False)
    else:
        finding = CodexStrictAuditRepairFinding("audit_repair_requires_manual_review", "unknown_audit_failure", "unknown_strict_failure")
        action = CodexStrictAuditRepairAction((pol.strict_verify_command,), False)
    return CodexStrictAuditRepairResult(pol, CodexStrictAuditRepairReport(finding, action))


def load_strict_output(path: Path) -> tuple[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return str(payload.get("stdout", "")), int(payload.get("exit_code", 1))
    return "", 1
