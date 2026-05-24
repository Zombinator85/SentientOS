# Codex PR metadata contract verifier/builder

`sentientos/codex_pr_metadata_contract.py` provides deterministic metadata-only verification and body building for Codex PR metadata before PR metadata creation.

## API
- `verify_pr_metadata(pr_title, pr_body, intended_commit_title=None)`
- `build_pr_body_from_rollup(rollup)`
- `parse_rollup_json(payload)`

## CLI
- Verify metadata:
  - `python scripts/codex_pr_metadata_contract.py verify --title "[codex:developer] ..." --body-file pr_body.md --intended-commit-title "[codex:developer] ..." --summary`
- Build body from rollup JSON:
  - `python scripts/codex_pr_metadata_contract.py build --rollup-json-file pr_rollup.json`

## Contract checks
- PR title must match `[codex:<subsystem>] ...`.
- Optional intended commit title must match exactly when supplied.
- PR body must include all full-validation sections:
  - full command matrix results
  - matrix runner --summary result
  - matrix runner --output result/path
  - targeted mypy result
  - baseline result
  - docs build result
  - prompt-boundary result
  - strict audit result
  - immutability verifier result
  - unresolved risks
- Body claims like "local tests only" / "touched tests only" fail verification.

This module is metadata-only and does not call GitHub, mutate branches/issues/comments, invoke Codex/providers/network/shell/subprocess, or grant runtime authority.
