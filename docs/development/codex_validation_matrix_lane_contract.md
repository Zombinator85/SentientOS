# Codex validation matrix lane contract

Metadata-only canonical lane registry and verifier used by Codex landing evidence checks.

## CLI

- `python -m scripts.codex_validation_matrix_lane_contract list`
- `python -m scripts.codex_validation_matrix_lane_contract verify --matrix-json-path <path>`
- `python -m scripts.codex_validation_matrix_lane_contract summary --matrix-json-path <path>`

## Contract behavior

- Required lanes must exist (alias accepted) and pass.
- Docs recovery is valid only when `docs_bootstrap`, `docs_check_deps_recheck`, and `docs_build` pass after a failed `docs_check_deps`.
- `required_failure_count` must match computed required lane failures.
- Unknown lanes are deterministic warnings by default.
