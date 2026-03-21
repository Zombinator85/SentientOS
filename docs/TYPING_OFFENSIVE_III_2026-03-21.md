# High-Density Typing Offensive III (2026-03-21)

This pass focused on the pulse/federation/runtime-core corridor and adjacent observatory/reporting consumers.

## Scope targeted

- Pulse transport/protocol surfaces:
  - `sentientos/daemons/pulse_bus.py`
  - `sentientos/daemons/pulse_federation.py`
- Federation governance/control and peer-state surfaces:
  - `sentientos/federated_governance.py`
  - `sentientos/federation/config.py`
  - `sentientos/federation/transport.py`
  - `sentientos/federation/poller.py`
  - `sentientos/federation/delta.py`
  - `sentientos/federation/federation_digest.py`
  - `sentientos/federation/symbol_ledger_daemon.py`
  - `sentientos/federation/enablement.py`
- Nearby runtime-core and observability consumers:
  - `sentientos/runtime/bootstrap.py`
  - `sentientos/observer_index.py`
  - `sentientos/observatory/fleet_health.py`

## Repo-wide mypy posture delta

- Before this pass: **2443** errors (`python -m mypy sentientos scripts api --hide-error-context --no-error-summary`).
- After this pass: **2412** errors (same command).
- Net reduction: **31** errors.

## Corridor density audit (before pass)

Highest-density remaining errors in the targeted corridor were grouped as:

1. **Pulse federation typing boundary leakage**
   - Modules: `pulse_federation.py`, `pulse_bus.py`
   - Families: `dict(object)` construction from loose mappings, return-value invariance, untyped third-party import.
   - Root cause: protocol/equivocation/replay payloads flowed as loose `object` / untyped dicts.
   - Payoff: high, because these payloads feed governance posture and observatory summaries.

2. **Governance digest/posture event coercion gaps**
   - Module: `federated_governance.py`
   - Families: `object has no attribute`, unused ignore, iterable assumptions.
   - Root cause: event payload fallbacks and trust-epoch component extraction lacked bounded coercion.
   - Payoff: high, because quorum/digest decisions consume these fields.

3. **Federation utility corridor coercion debt**
   - Modules: `federation/config.py`, `federation/transport.py`, `federation/poller.py`, `federation/delta.py`, `federation_digest.py`, `symbol_ledger_daemon.py`, `enablement.py`.
   - Families: `call-overload` on `int`, missing annotations, literal narrowing, generic parameter omissions.
   - Root cause: widespread permissive mapping ingestion around peer/replay/config surfaces.
   - Payoff: medium-high; removes propagation into runtime and reporting lanes.

4. **Observatory/reporting consumer fallthrough**
   - Modules: `observer_index.py`, `observatory/fleet_health.py`
   - Families: scalar coercion from `object`, return-value invariance, variable redefinition.
   - Root cause: ingestion from broad-lane structured JSON without typed coercion helpers.
   - Payoff: medium-high; improves downstream health summary reliability.

## What improved in this pass

- Added explicit mapping/int coercion adapters at pulse-federation and governance boundaries.
- Tightened protocol/replay/equivocation payload handling to avoid loose `object` propagation.
- Made replay severity and payload envelopes stricter in federation delta/poller transport paths.
- Fixed runtime bootstrap optional integration typing boundary.
- Stabilized observatory/observer report typing with explicit coercion paths.

## Corridor results

The following targeted modules were reduced to zero mypy errors in repo-wide mode:

- `sentientos/daemons/pulse_bus.py`
- `sentientos/daemons/pulse_federation.py`
- `sentientos/federated_governance.py`
- `sentientos/runtime/bootstrap.py`
- `sentientos/federation/config.py`
- `sentientos/federation/enablement.py`
- `sentientos/federation/poller.py`
- `sentientos/federation/symbol_ledger_daemon.py`
- `sentientos/federation/federation_digest.py`
- `sentientos/federation/delta.py`
- `sentientos/observer_index.py`
- `sentientos/observatory/fleet_health.py`
- `sentientos/federation/transport.py`

## Ratchet/protected-surface posture

- No ratchet policy expansion was asserted in this pass.
- `python scripts/mypy_ratchet.py --report` remains `status=ok` and indicates no protected-scope regressions.
- Promotion to stricter ratchet treatment is plausible for the now-clean modules above, but deferred to a dedicated ratchet policy pass.

## Deferred/high-density next targets

Given current repo-wide density, likely next high-payoff clusters after this corridor pass are:

- `sentientos/lab/wan_federation.py`
- `sentientos/governance/intentional_forgetting.py`
- runtime test-typing debt under `sentientos/tests/runtime/*`
- broad legacy typing families (`Missing type parameters`, `no-untyped-def`) outside protected corridor

This pass intentionally stayed within the pulse/federation/runtime-core and adjacent observatory corridor.
