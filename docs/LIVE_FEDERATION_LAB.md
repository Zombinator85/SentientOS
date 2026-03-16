# Live Federation Lab

The live federation lab runs **real local SentientOS node workspaces and processes** to exercise runtime, governor, trust, replay, incident, and protected-corridor-compatible operator surfaces together.

## Launch

```bash
python -m sentientos.ops lab federation --nodes 3 --seed 42 --scenario healthy_3node --mode daemon --json
python -m sentientos.ops lab federation --scenario quorum_failure --mode daemon --emit-bundle --json
python -m sentientos.ops lab federation --mode auto --nodes 3 --json
```

Also available:

```bash
make federation-lab MODE=daemon
make federation-lab-scenario SCENARIO=quorum_failure NODES=3 SEED=42 MODE=daemon
make federation-lab-clean
```

## Runtime modes

- `--mode daemon`: launches the real runtime daemon entrypoint (`scripts/orchestrator_daemon.py`) per node with deterministic node runtime roots and deterministic per-node identity/port assignment.
- `--mode worker`: launches the existing bounded worker loop (`sentientos.lab.node_worker`) per node.
- `--mode auto` (default): deterministic selection; uses daemon mode when the daemon entrypoint is present, otherwise worker mode.

The run summary always records both:

- `runtime_mode_requested`
- `runtime_mode_resolved`

## How it differs from deterministic simulation

- `simulate federation` is deterministic model/surface simulation.
- `lab federation` creates isolated runtime roots under `glow/lab/federation/<run_id>/nodes/node-XX`, bootstraps each node, starts runtime processes (daemon or worker), injects bounded faults, and evaluates live outcomes.

## Supported live scenarios

All core live scenarios support daemon parity:

- `healthy_3node`
- `quorum_failure`
- `replay_storm`
- `reanchor_continuation`
- `pressure_local_safety`

Use `python -m sentientos.ops lab federation --list-scenarios --json` for machine-readable details.

## Key artifacts

Run-root files now include daemon lifecycle and observability evidence:

- `run_metadata.json`
- `process_transitions.jsonl`
- `scenario_injection_log.jsonl`
- `event_timeline.json`
- `artifact_manifest.json`
- `run_summary.json`

Each node also records runtime process snapshots and per-node logs under `nodes/node-XX/glow/lab/`.
