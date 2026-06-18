# Codex Validation and Landing Contract

## Two-phase finalizer contract
1. Before commit, run `python scripts/codex_finalize_landing.py finalize --phase pre-commit ...`.
   - Commit only if status is `ready_to_commit`.
   - Intended source/doc/test changes may be present when declared via `--changed-file`, inferred from tracked changes with `--allow-current-tracked-changes`, and inferred from safe untracked task files with `--allow-current-task-files` (pre-commit only).
2. After commit and before PR metadata/final report, run `python scripts/codex_finalize_landing.py finalize --phase pr-metadata ...` (or `post-commit`).
   - Create/update PR metadata only if status is `ready_for_pr_metadata`.
   - Tree must be clean except allowed generated artifacts that are cleaned successfully.

## Required evidence
Run the validation required by `AGENTS.md`, the task profile/template, and the changed surfaces. Focused tests alone are insufficient when matrix, governance, landing, audit, supervisor, proof, or capability rails apply.

The mandatory landing sequence remains: bootstrap -> required validation -> pre-commit finalizer `ready_to_commit` -> commit -> post-commit/pr-metadata finalizer `ready_for_pr_metadata` -> PR metadata guard `pr_metadata_guard_ready` -> `make_pr`.

Situational validation selects the relevant lanes without weakening the landing contract:

- docs build when docs changed;
- prompt-boundary checks when context-hygiene or prompt-boundary docs/scripts are touched;
- targeted mypy when Python surfaces changed;
- lane/matrix/capability tests when those surfaces changed;
- broader regression at threshold/risk points or when required by existing doctrine.

Run `python scripts/codex_landing_supervisor.py evaluate --title "..." --intended-commit-title "..." --matrix-json-path /tmp/work_item_review_packet_matrix.json --summary` after matrix and PR gate when the landing rail requires supervisor evidence; do not finalize unless decision is `ready_to_commit` or `ready_for_pr_metadata`.

## Dirty tree rules
- Pre-commit: declared intended task changes are allowed.
- Post-commit/pr-metadata: source dirty files block.
- Unknown dirty files always block.
- Generated runtime artifacts must be cleaned or block.


## Self-sealing requirement
- Validation-only seal turns should not be necessary for normal implementation tasks.
- If finalizer tooling is available, the same task must self-seal using both phases.
- Missing post-commit/pr-metadata finalizer before PR metadata is a task-owned failure.
- Missing stale-evidence refresh in the same task (when strict-audit/cleanup state changed) is task-owned failure.
- Do not request a validation-only follow-up when the only blocker is stale matrix/gate/supervisor/finalizer evidence.
- Do not defer post-commit sealing to follow-up turns when implementation changes occurred.

## Bootstrap and PR metadata guard hard stops
- Run the bootstrapper before implementation. If bootstrap status is `blocked`, generated prompt/scaffold artifacts are diagnostic only and must include `BLOCKED_DO_NOT_IMPLEMENT`; stop, report the blocker, and do not implement, commit, or `make_pr` from that artifact.
- Implement only from `ready` or `ready_with_warnings` bootstrap output.
- After the post-commit/pr-metadata finalizer returns `ready_for_pr_metadata`, run `python scripts/codex_pr_metadata_guard.py verify ...` and require `pr_metadata_guard_ready` before PR metadata or `make_pr`.
- A finalizer artifact alone is not enough when the PR metadata guard says blocked.
- Focused tests passing without a ready PR metadata guard is not a complete landing.

Strict landing sequence: run bootstrapper; stop if blocked; implement only if ready/ready_with_warnings; run required validation; run pre-commit finalizer and require `ready_to_commit`; commit; run post-commit/pr-metadata finalizer and require `ready_for_pr_metadata`; run PR metadata guard and require `pr_metadata_guard_ready`; only then `make_pr`.
