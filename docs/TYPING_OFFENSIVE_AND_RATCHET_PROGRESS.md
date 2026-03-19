# Typing Offensive and Ratchet Progress

This pass focuses on high-value mature surfaces linked to federation, pulse reliability, and observability/reporting.

## Latest pass (2026-03-19)

- Comprehensive high-density offensive summary is recorded in `docs/TYPING_OFFENSIVE_PROGRESS.md`.
- Repo-wide `mypy sentientos scripts api` moved from **2511** to **2418** errors in this pass.
- Mature ops/simulation/lab/observatory modules targeted in this pass are now clean:
  - `sentientos/ops/__main__.py`
  - `sentientos/simulation/federation.py`
  - `sentientos/lab/federation_lab.py`
  - `sentientos/lab/truth_oracle.py`
  - `sentientos/observatory/artifact_index.py`

## Scope of this offensive

- Pulse bus and federation reliability paths (`sentientos/daemons/*`).
- Federation CLI and reconciliation surfaces (`sentientos/federation/*`).
- Observatory/dashboard status typing cleanup (`sentientos/dashboard/status_source.py`).
- Failure-digest classification reliability (`scripts/analyze_test_failures.py`).

## Ratchet posture

- **No debt hiding**: remaining global `mypy scripts/ sentientos/` debt is still visible.
- **Higher signal quality**: key baseline lanes now fail in more deterministic classes.
- **Incremental offensive model**: reduce high-value error clusters first, then continue ratcheting across legacy modules.

## Deferred debt policy

Deferred typing/runtime debt is acceptable only when:

- it is not in protected corridor paths,
- it is clearly classified by machine-readable outputs,
- and it does not degrade enforcement signals for trust, epoch, quorum, digest, or contradiction/release gates.

## Next pass recommendation

- Continue focused typing cleanup in observatory/governance reporting modules.
- Expand deterministic failure classification beyond current broad classes.
- Ratchet mypy by reducing high-density modules instead of scattered low-impact files.
