# High-Density Typing Offensive Progress (2026-03-19)

## Repo-wide failure-density audit

Baseline command:

- `mypy sentientos scripts api --show-column-numbers --no-color-output`

Before this pass, parser rollup identified **2511** errors.

Top clusters before:

- `sentientos/tests`: 390
- `scripts`: 153
- `sentientos/lab`: 119
- `architect_daemon.py`: 100
- `sentientos/governance`: 77
- `task_executor.py`: 71

Top error families before:

- `arg-type`: 509
- `attr-defined`: 399
- `type-arg`: 287
- `no-untyped-def`: 282
- `call-overload`: 231
- `union-attr`: 163

## High-density offensive executed

This pass targeted mature, high-value surfaces aligned with operations, simulation/lab, and observatory reporting:

- `sentientos/ops/__main__.py`
- `sentientos/simulation/federation.py`
- `sentientos/lab/federation_lab.py`
- `sentientos/lab/truth_oracle.py`
- `sentientos/observatory/artifact_index.py`

### Change themes

- Added safe typed adapters (`_as_dict`, `_as_list`, `_as_int`, `_as_float`) to constrain `object` propagation at module boundaries.
- Replaced ad-hoc chained `.get()` access with explicit narrowing helpers.
- Tightened runtime mode typing in ops CLI (`Literal["auto", "worker", "daemon"]`) while preserving existing behavior.
- Fixed payload mutation patterns that were forcing unstable inferred unions in simulation/lab reports.
- Hardened observatory artifact-link extraction against ambiguous JSON shapes.

## Results

After this pass, the same repo-wide command reports **2418** errors (**-93 net**).

### File-level deltas in targeted modules

- `sentientos/ops/__main__.py`: 24 -> 0
- `sentientos/simulation/federation.py`: 23 -> 0
- `sentientos/lab/federation_lab.py`: 22 -> 0
- `sentientos/lab/truth_oracle.py`: 21 -> 0
- `sentientos/observatory/artifact_index.py`: 2 -> 0

### Cluster-level movement

- `sentientos/lab`: 119 -> 95
- `arg-type`: 509 -> 495
- `attr-defined`: 399 -> 380
- `call-overload`: 231 -> 222
- `union-attr`: 163 -> 145

## Ratchet/protected-surface posture

- No ratchet baselines were loosened.
- No protected corridor semantics were altered.
- This pass improves type signal quality on operational/reporting surfaces, making these modules stronger candidates for tighter per-surface ratchet treatment in follow-up passes.

## Remaining heavy clusters (next candidates)

1. `sentientos/tests`
2. `scripts`
3. `architect_daemon.py`
4. `task_executor.py`
5. `sentientos/shell`
6. `sentientos/governance`

Recommended next offensive: another high-density pass focused on `architect_daemon.py`, `task_executor.py`, and `sentientos/shell` cross-module `object` propagation.
