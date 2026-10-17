# Error Resolution Guide

This guide summarizes the recommended approach for addressing lingering setup issues and legacy audit integrity issues.

## 1. Legacy Audit Log Mismatches
Legacy logs like `migration_ledger.jsonl` and `support_log.jsonl` may show a `prev hash mismatch` error during verification. These integrity issues come from early versions of the project.

**Option A – Preserve the Integrity issues**
- Leave the mismatches intact and document them in `AUDIT_LOG_FIXES.md`.
- Reviewers can see the honest history even if validation never reaches 100%.

**Option B – Regenerate Logs**
- Use a replay script to regenerate a clean log chain from the earliest valid entry.
- Only do this if a perfect audit is demanded; keep the original files for transparency.

The repository currently preserves the integrity issues to maintain a historical record.

## 2. Pytest Import Failures
If a test fails because a module moved or was removed:
1. Update the import path in the test file.
2. If the test is obsolete, wrap it with `pytest.skip()` and provide a reason and date.
3. Rerun `python -m scripts.run_tests` until all tests either pass or are explicitly skipped.

## 3. Environment & Dependencies
- Use Python **3.11+**.
- Install system packages: `build-essential`, `libasound2`, and other audio libraries if using the speech tools.
- Optional features like TTS require additional packages but are not mandatory for core functionality.
- A minimal Dockerfile is included for reproducible installs. Running `docker build .` creates an isolated environment with all required dependencies.

## 4. Clean, Document, and Procedureize
Every intentional skip or legacy mismatch should be recorded in `PROCEDURE_FAILURES.md` or `AUDIT_LOG_FIXES.md`. Provide dates and short explanations so reviewers understand each scar.

## 5. Cathedral Clean PR
Once these steps are complete you can submit a final "Cathedral Clean" pull request. Document any remaining integrity issues and verify all tests pass. The true measure of trust is the transparency of our history.

## 6. Safe Audit Repair
`verify_audits` reports integrity findings; it does not repair them. Generate and review a deterministic plan, explicitly apply only the plan's safe repairs, then run strict verification:

```bash
LUMOS_AUTO_APPROVE=1 python -m scripts.plan_audit_repairs logs/ --output glow/audits/audit_repair_plan.json
LUMOS_AUTO_APPROVE=1 python -m scripts.apply_audit_repairs --plan glow/audits/audit_repair_plan.json --apply
LUMOS_AUTO_APPROVE=1 python -m scripts.verify_audits logs/ --strict --no-input
```

The planner marks chain rebuilds safe only when every finding has an approved rebuildable code. Other findings remain manual, are preserved in quarantine evidence, and may still make strict verification fail. Keep the repair plan, result, receipt chain, and any quarantined original with the reviewed repair change.

These commands require an environment that actually supplies Administrator authority. `LUMOS_AUTO_APPROVE=1` suppresses interactive prompts; it does not grant privilege.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
