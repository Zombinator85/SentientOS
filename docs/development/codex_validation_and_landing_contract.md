# Codex Validation and Landing Contract

## Two-phase finalizer contract
1. Before commit, run `python scripts/codex_finalize_landing.py finalize --phase pre-commit ...`.
   - Commit only if status is `ready_to_commit`.
   - Intended source/doc/test changes may be present when declared via `--changed-file` or inferred from tracked changes with `--allow-current-tracked-changes` (pre-commit only).
2. After commit and before PR metadata/final report, run `python scripts/codex_finalize_landing.py finalize --phase pr-metadata ...` (or `post-commit`).
   - Create/update PR metadata only if status is `ready_for_pr_metadata`.
   - Tree must be clean except allowed generated artifacts that are cleaned successfully.

## Required evidence
Run focused tests, targeted mypy, baseline, matrix summary/output, PR landing gate, landing supervisor, docs build, prompt-boundary checks, strict audits, and audit immutability.

Run `python scripts/codex_landing_supervisor.py evaluate --title "..." --intended-commit-title "..." --matrix-json-path /tmp/work_item_review_packet_matrix.json --summary` after matrix and PR gate; do not finalize unless decision is `ready_to_commit` or `ready_for_pr_metadata`.

## Dirty tree rules
- Pre-commit: declared intended task changes are allowed.
- Post-commit/pr-metadata: source dirty files block.
- Unknown dirty files always block.
- Generated runtime artifacts must be cleaned or block.


## Self-sealing requirement
- Validation-only seal turns should not be necessary for normal implementation tasks.
- If finalizer tooling is available, the same task must self-seal using both phases.
- Missing post-commit/pr-metadata finalizer before PR metadata is a task-owned failure.
- Do not defer post-commit sealing to follow-up turns when implementation changes occurred.
