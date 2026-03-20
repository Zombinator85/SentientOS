# Typing Offensive and Ratchet Progress

This pass focuses on high-value mature surfaces linked to trust/federation runtime behavior, observatory dashboard/status aggregation, and drift diagnostics.

## Latest pass (2026-03-19, Offensive II)

- Comprehensive high-density offensive summary is recorded in `docs/TYPING_OFFENSIVE_PROGRESS.md`.
- Repo-wide `mypy scripts/ sentientos/` moved from **2516** to **2463** errors in this pass (**-53**).
- Modules reduced to zero in this pass:
  - `sentientos/trust_ledger.py`
  - `sentientos/observatory/fleet_health.py`
  - `sentientos/diagnostics/drift_detector.py`
  - `sentientos/diagnostics/drift_alerts.py`

## Scope of this offensive

- Trust/federation-adjacent ledger normalization and probe-state typing.
- Observatory fleet-health dashboard/detail aggregation typing.
- Runtime drift detector and drift alert payload narrowing.

## Ratchet posture

- **No debt hiding**: remaining global `mypy scripts/ sentientos/` debt remains visible.
- **No standards loosening**: no ratchet baseline expansion was used to mask errors.
- **Improved protected-surface readiness**: selected trust/observability modules are now clean and better candidates for future stricter ratchet coverage.

## Deferred debt policy

Deferred typing/runtime debt is acceptable only when:

- it is not in protected corridor paths,
- it is clearly classified by machine-readable outputs,
- and it does not degrade enforcement signals for trust, epoch, quorum, digest, or contradiction/release gates.

## Next pass recommendation

- Runtime-heavy: `architect_daemon.py`, `task_executor.py`.
- Dashboard/reporting: `scripts/tooling_status.py`.
- Federation/lab adjacency: `sentientos/lab/wan_federation.py`, then `sentientos/shell/__init__.py`.
