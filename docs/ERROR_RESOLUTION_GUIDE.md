# Error Resolution Guide

This guide summarizes the recommended approach for addressing lingering setup issues and legacy audit wounds.

## 1. Legacy Audit Log Mismatches
Legacy logs like `migration_ledger.jsonl` and `support_log.jsonl` may show a `prev hash mismatch` error during verification. These wounds come from early versions of the project.

**Option A – Preserve the Wounds**
- Leave the mismatches intact and document them in `AUDIT_LOG_FIXES.md`.
- Reviewers can see the honest history even if validation never reaches 100%.

**Option B – Regenerate Logs**
- Use a replay script to regenerate a clean log chain from the earliest valid entry.
- Only do this if a perfect audit is demanded; keep the original files for transparency.

The repository currently preserves the wounds to maintain a historical record.

## 2. Pytest Import Failures
If a test fails because a module moved or was removed:
1. Update the import path in the test file.
2. If the test is obsolete, wrap it with `pytest.skip()` and provide a reason and date.
3. Rerun `pytest` until all tests either pass or are explicitly skipped.

## 3. Environment & Dependencies
- Use Python **3.11+**.
- Install system packages: `build-essential`, `libasound2`, and other audio libraries if using the speech tools.
- Optional features like TTS require additional packages but are not mandatory for core functionality.
- A minimal Dockerfile is included for reproducible installs. Running `docker build .` creates an isolated environment with all required dependencies.

## 4. Clean, Document, and Ritualize
Every intentional skip or legacy mismatch should be recorded in `RITUAL_FAILURES.md` or `AUDIT_LOG_FIXES.md`. Provide dates and short explanations so reviewers understand each scar.

## 5. Cathedral Clean PR
Once these steps are complete you can submit a final "Cathedral Clean" pull request. Document any remaining wounds and verify all tests pass. The true measure of trust is the transparency of our history.
