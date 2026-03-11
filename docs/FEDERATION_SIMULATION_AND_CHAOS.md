# Federation Simulation + Chaos Validation Wing

This wing adds deterministic multi-node federation simulation to SentientOS without introducing new constitutional/runtime/federation subsystems.

## Entrypoints

- `python -m sentientos.ops simulate federation --scenario healthy_3node --json`
- `python -m sentientos.ops simulate federation --scenario quorum_failure --emit-bundle --json`
- `python scripts/simulate_federation.py --scenario replay_storm --json`
- `make simulate-federation`

## Deterministic model

Each simulation run is bounded and reproducible by:

- explicit scenario id
- explicit node count
- explicit deterministic seed
- explicit phase + injection plan

Run directory:

- `glow/simulation/<scenario>_seed<seed>_nodes<n>/`

## What is exercised

The simulation wing stresses existing surfaces:

- node bootstrap and health posture composition
- federation governance digest and trust-epoch compatibility behaviors
- quorum admit/deny outcomes
- replay flood duplicate pressure
- degraded audit trust + re-anchor continuation recognition
- governor pressure and local safety precedence
- incident bundle generation under stress

## Artifacts

Each run emits:

- `scenario_report.json`
- per-node `glow/simulation/status_snapshot.json`
- `event_injection_log.jsonl`
- optional incident bundles from selected nodes
- `bundle_manifest.json` (hashes and file sizes)

All injections are explicit and recorded in `event_injection_log.jsonl`.
