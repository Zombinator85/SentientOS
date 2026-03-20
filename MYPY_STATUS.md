# SentientOS mypy baseline (ratchet mode)

This repository now runs mypy in **canonical baseline + ratchet** mode from one deterministic scoreboard.

## Canonical baseline definition

- Authoritative command:
  - `python scripts/mypy_ratchet.py`
- Authoritative config/options:
  - `mypy.ini` is the canonical config file.
  - Scope roots and exclusions are policy-driven via `glow/contracts/mypy_policy.json` (`canonical_roots`, `canonical_exclude_globs`).
- Current canonical roots:
  - `["."]` (all git-tracked Python files)
- Current canonical excludes:
  - `tests/*`, `escrow/*`, `godot_avatar_demo/*`, `glow/*`, `pulse/*`

## Current baseline snapshot

- Baseline artifact: `glow/contracts/mypy_baseline.json`
- Canonical scoreboard artifacts:
  - `glow/contracts/canonical_typing_baseline.json`
  - `glow/contracts/typing_cluster_summary.json`
  - `glow/contracts/typing_ratchet_status.json`
  - `glow/contracts/final_typing_baseline_digest.json`
- Comparable repo-wide error total:
  - **0** errors as of this normalization pass (`python scripts/mypy_ratchet.py`)
  - Source of truth remains `canonical_typing_baseline.json:error_count` for future passes.
- Type-family distribution for current snapshot is emitted in
  `canonical_typing_baseline.json:error_count_by_code`.

## Policy

- Policy artifact: `glow/contracts/mypy_policy.json`
- Protected surfaces include runtime, federation, simulation, ops, audit, and verify modules.
- Forge and ratchet tooling stays in strict mode where feasible.
- Existing debt is tracked, not hidden; regression is blocked by ratchet checks.

## Ratchet commands

- Repo-wide ratchet check:
  - `python scripts/mypy_ratchet.py`
- PR-touched-surface ratchet check:
  - `python -m scripts.mypy_ratchet --touched-surface`
- Baseline/policy report:
  - `python scripts/mypy_ratchet.py --report`
- Refresh baseline (maintainers only):
  - `SENTIENTOS_ALLOW_BASELINE_REFRESH=1 python -m scripts.mypy_ratchet --refresh`

## Intentional deferred debt

- Legacy root-level scripts and dynamic orchestration modules with large pre-existing typing debt remain deferred.
- The ratchet prevents new debt in protected surfaces while cleanup proceeds incrementally.
- `typing_ratchet_status.json` distinguishes:
  - ratcheted (new signatures not in baseline),
  - deferred debt (baseline signatures still present),
  - protected regressions,
  - promotable protected modules that reached zero errors.
