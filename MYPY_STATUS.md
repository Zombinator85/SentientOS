# SentientOS mypy baseline (ratchet mode)

This repository currently runs mypy in **baseline + ratchet** mode for `scripts/` and `sentientos/`.

## Current baseline snapshot

- Baseline artifact: `glow/contracts/mypy_baseline.json`
- Baseline volume: **2078** errors across **326** modules
- Highest-noise categories (count):
  - `arg-type` (450)
  - `type-arg` (311)
  - `no-untyped-def` (264)
  - `attr-defined` (241)
  - `call-overload` (142)

## Policy

- Policy artifact: `glow/contracts/mypy_policy.json`
- Protected surfaces include runtime, federation, simulation, ops, audit, and verify modules.
- Forge and ratchet tooling stays in strict mode where feasible.
- Existing debt is tracked, not hidden; regression is blocked by ratchet checks.

## Ratchet commands

- Repo-wide ratchet check:
  - `python -m scripts.mypy_ratchet`
- PR-touched-surface ratchet check:
  - `python -m scripts.mypy_ratchet --touched-surface`
- Baseline/policy report:
  - `python -m scripts.mypy_ratchet --report`
- Refresh baseline (maintainers only):
  - `SENTIENTOS_ALLOW_BASELINE_REFRESH=1 python -m scripts.mypy_ratchet --refresh`

## Intentional deferred debt

- Legacy root-level scripts and dynamic orchestration modules with large pre-existing typing debt remain deferred.
- The ratchet prevents new debt in protected surfaces while cleanup proceeds incrementally.
