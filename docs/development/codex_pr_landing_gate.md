# Codex PR landing gate

`sentientos/codex_pr_landing_gate.py` is the deterministic metadata-only final pre-`make_pr` gate.

It composes:
- PR metadata contract checks,
- PR validation evidence checks,
- validation matrix lane contract checks.

CLI: `python -m scripts.codex_pr_landing_gate verify|build-body|gate`.

## Relationship to PR metadata guard
The PR landing gate remains a required finalizer lane, but it is not the last authority before `make_pr`. The repo-local PR metadata guard validates concrete finalizer proof artifacts and the matrix artifact after the post-commit/pr-metadata finalizer. `make_pr` is forbidden unless `python scripts/codex_pr_metadata_guard.py verify ... --summary` returns `pr_metadata_guard_ready`.
