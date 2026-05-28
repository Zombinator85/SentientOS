# Reviewer's Quickstart

This one-page checklist gives reviewers a deterministic snapshot of audit and
federation posture using the current command surface.

1. Clone the repository and install dependencies (`bash setup_env.sh`).
2. Verify audit chains:
   ```bash
   verify_audits --strict
   ```
3. Check read-only runtime diagnostics:
   ```bash
   python -m sentientos doctor
   ```
4. Check fleet observability rollups:
   ```bash
   python -m sentientos.ops observatory fleet --json
   python -m sentientos.ops observatory artifacts --json
   ```
5. Check node and constitution posture:
   ```bash
   python -m sentientos.ops node health --json
   python -m sentientos.ops constitution verify --json
   ```
6. Run the work-item review-packet validation matrix (continues after failures and reports every step):
   ```bash
   python scripts/run_work_item_review_packet_matrix.py --summary
   ```

   The runner executes the full proof matrix (tests, targeted mypy, baseline ratchet, docs deps/build, prompt-boundary scan, strict audits, and audit immutability), auto-bootstraps docs deps when `--check-deps` fails, and exits non-zero at the end if required checks fail.

7. Optional: run/inspect individual gates directly when debugging:
   ```bash
   python scripts/check_mypy_baseline.py
   python scripts/build_docs.py --check-deps
   python scripts/build_docs.py
   ```

   The baseline/ratchet contract is documented in [mypy_baseline_ratchet.md](architecture/mypy_baseline_ratchet.md).

For terminology translation between public engineering language and internal
codenames, see [PUBLIC_LANGUAGE_BRIDGE.md](PUBLIC_LANGUAGE_BRIDGE.md).

SentientOS prioritizes operator accountability, auditability, and safe
shutdown.


## Codex landing doctrine and templates
- Root doctrine: [`AGENTS.md` Codex operating instructions](../AGENTS.md)
- Whole-system task template: [`docs/development/codex_whole_system_task_template.md`](development/codex_whole_system_task_template.md)
- Narrow-repair template: [`docs/development/codex_narrow_repair_task_template.md`](development/codex_narrow_repair_task_template.md)
- Validation/landing contract: [`docs/development/codex_validation_and_landing_contract.md`](development/codex_validation_and_landing_contract.md)
- PR metadata guard: [`docs/development/codex_pr_metadata_guard.md`](development/codex_pr_metadata_guard.md)
- Validation matrix runner: [`scripts/run_work_item_review_packet_matrix.py`](../scripts/run_work_item_review_packet_matrix.py)
