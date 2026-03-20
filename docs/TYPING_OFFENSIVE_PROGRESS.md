# High-Density Typing Offensive Progress (2026-03-19)

## Repo-wide failure-density audit (Offensive II baseline)

Baseline command:

- `mypy scripts/ sentientos/`

Before this pass, repo-wide output reported **2516** errors.

Top mature/high-value clusters before this pass (from file-density rollup):

- `architect_daemon.py`: 100
- `task_executor.py`: 71
- `sentientos/lab/wan_federation.py`: 65
- `sentientos/shell/__init__.py`: 65
- `scripts/tooling_status.py`: 27
- `sentientos/observatory/fleet_health.py`: 18
- `sentientos/diagnostics/drift_detector.py`: 17
- `sentientos/trust_ledger.py`: 16

Targeted error families in selected clusters were dominated by:

- `call-overload` on `int(...)`/`float(...)` from `object`
- `union-attr` from nullable/list-or-dict JSON payloads
- `attr-defined` on un-narrowed `object` payload access

## High-density typing offensive II executed

This pass targeted the next dense mature clusters across trust/federation, dashboard/reporting, and runtime diagnostics:

- `sentientos/trust_ledger.py`
- `sentientos/observatory/fleet_health.py`
- `sentientos/diagnostics/drift_detector.py`
- `sentientos/diagnostics/drift_alerts.py`

### Change themes

- Added local typed normalization helpers (`_as_int`, `_as_rows`, `_as_mapping`, `_probe_history_from`) to stop `object` propagation at source boundaries.
- Replaced direct `int/float` coercion on untyped payload objects with explicit narrowing adapters.
- Normalized optional silhouette/report payloads before aggregation to avoid nullable-union spread through runtime paths.
- Kept behavior stable (same artifact contract/writes and trust-state derivation semantics), while making payload handling explicit for mypy.

## Results

After this pass, the same repo-wide command reports **2463** errors (**-53 net**).

### File-level deltas in targeted modules

- `sentientos/trust_ledger.py`: 16 -> 0
- `sentientos/observatory/fleet_health.py`: 18 -> 0
- `sentientos/diagnostics/drift_detector.py`: 17 -> 0
- `sentientos/diagnostics/drift_alerts.py`: 2 -> 0

### Cluster-level payoff in this pass

- Trust/federation-adjacent cluster (`trust_ledger`) now clean.
- Observatory dashboard/status cluster (`fleet_health`) now clean.
- Runtime diagnostics drift surfaces now clean.
- Biggest drops in targeted families: `call-overload`, `union-attr`, and `attr-defined` across selected modules.

## Ratchet/protected-surface posture

- No ratchet baselines were loosened.
- No protected corridor/trust epoch/quorum/digest/contradiction-policy behavior was altered.
- This pass improves typing signal quality on mature trust and observability surfaces and raises confidence for future ratchet expansion around these now-clean modules.

## Remaining heavy clusters (next candidates)

1. `architect_daemon.py`
2. `task_executor.py`
3. `sentientos/shell/__init__.py`
4. `sentientos/lab/wan_federation.py`
5. `scripts/tooling_status.py`
6. `memory_manager.py` / `sentientos/narrative_synthesis.py`

Recommended next offensive: runtime-heavy `architect_daemon.py` + `task_executor.py`, then a dedicated dashboard/reporting pass for `scripts/tooling_status.py`.
