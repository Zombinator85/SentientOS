from sentientos.codex_strict_audit_repair import CodexStrictAuditRepairRequest, diagnose_strict_audit_repair

def test_known_chain_break_classifies_generated_runtime_drift() -> None:
    txt = "chain break in pulse/audit/privileged_audit.runtime.jsonl"
    res = diagnose_strict_audit_repair(CodexStrictAuditRepairRequest(txt, 1))
    assert res.report.finding.classification == "generated_runtime_artifact_drift"
    assert res.report.finding.status == "audit_repair_ready"

def test_unknown_failure_requires_manual_review() -> None:
    res = diagnose_strict_audit_repair(CodexStrictAuditRepairRequest("mystery fail", 1))
    assert res.report.finding.status == "audit_repair_requires_manual_review"

def test_policy_failure_not_auto_repair() -> None:
    res = diagnose_strict_audit_repair(CodexStrictAuditRepairRequest("audit policy violation", 1))
    assert res.report.finding.classification == "task_caused_code_audit_failure"

def test_repair_plan_has_rechecks() -> None:
    txt = "chain break in pulse/audit/privileged_audit.runtime.jsonl"
    res = diagnose_strict_audit_repair(CodexStrictAuditRepairRequest(txt, 1))
    cmds = res.report.action.commands
    assert "python verify_audits.py --strict" in cmds
    assert "python scripts/audit_immutability_verifier.py" in cmds
