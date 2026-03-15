# Live Federation Lab

The live federation lab runs **real local SentientOS node workspaces and processes** to exercise runtime, governor, trust, replay, and incident surfaces together.

## Launch

```bash
python -m sentientos.ops lab federation --nodes 3 --seed 42 --scenario healthy_3node --json
```

Also available:

```bash
make federation-lab
make federation-lab-scenario SCENARIO=quorum_failure NODES=3 SEED=42
make federation-lab-clean
```

## How it differs from deterministic simulation

- `simulate federation` is deterministic model/surface simulation.
- `lab federation` creates isolated runtime roots under `glow/lab/federation/<run_id>/nodes/node-XX`, bootstraps each node, starts worker processes, injects bounded faults, and evaluates live outcomes.

## Supported live scenarios

- `healthy_3node`
- `quorum_failure`
- `replay_storm`
- `reanchor_continuation`
- `pressure_local_safety`

Use `python -m sentientos.ops lab federation --list-scenarios --json` for machine-readable details including `live_capable` and `simulated_only` flags.
