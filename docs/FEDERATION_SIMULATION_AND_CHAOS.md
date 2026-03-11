# Federation Simulation + Chaos Validation Wing

This wing provides deterministic multi-node federation simulation as a release-gate surface without introducing new constitutional/runtime/federation subsystems.

## Entrypoints

- Single scenario: `python -m sentientos.ops simulate federation --scenario healthy_3node --json`
- Canonical baseline gate: `python -m sentientos.ops simulate federation --baseline --json`
- List scenario catalog: `python -m sentientos.ops simulate federation --list-scenarios --json`
- Script wrapper: `python scripts/simulate_federation.py --baseline --json`

## Canonical baseline suite

The baseline suite is declared in:

- `sentientos/simulation/federation_baseline_manifest.json`

Scenarios currently included:

- `healthy_3node`
- `quorum_failure`
- `replay_storm`
- `reanchor_continuation`
- `pressure_local_safety`

All listed scenarios are currently **release-gating**.

## Deterministic policy

Determinism is explicit and auditable:

- baseline manifest has deterministic seed policy + per-scenario seed values
- scenario run IDs are deterministic (`<scenario>_seed<seed>_nodes<n>`)
- baseline report omits wall-clock timestamps to keep output stable across re-runs
- chaos/fault injections are explicit and ledgered in `event_injection_log.jsonl`

## Gate output + exit behavior

`--baseline` writes:

- `glow/simulation/baseline_report.json`

The baseline report includes:

- per-scenario pass/fail
- release-gating flag
- oracle expectation checks
- required artifact expectation checks
- missing artifact list (if any)
- incident-bundle compatibility payload for failed scenarios

Exit code behavior:

- `0`: all release-gating scenarios passed
- `1`: one or more release-gating scenarios failed
- `2`: command/surface misuse (unknown scenario, argument contract violations)

## Artifacts

Each scenario run emits:

- `scenario_report.json`
- per-node `glow/simulation/status_snapshot.json`
- `event_injection_log.jsonl`
- optional incident bundles
- `bundle_manifest.json` (hash + size ledger)

Baseline suite emits:

- `glow/simulation/baseline_report.json` (deterministic release-gate summary)
