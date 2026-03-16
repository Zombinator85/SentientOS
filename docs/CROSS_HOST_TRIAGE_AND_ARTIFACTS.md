# Cross-Host Triage and Artifacts

Each WAN lab run emits correlated host/node artifacts under `glow/lab/wan/<run_id>/`.

## Core artifacts

- `host_manifest.json`
- `topology_manifest.json`
- `host_process_transitions.jsonl`
- `fault_timeline.json`
- `wan_faults.jsonl`
- `convergence_summary.json`
- `final_cluster_digest.json`
- `artifact_hash_manifest.json`
- `run_summary.json`

## Per-host/per-node material

Per host runtime roots include per-node:

- `glow/lab/node_identity.json`
- `glow/lab/wan_status.json` (if WAN faults touched node)
- `glow/constitution/constitution_summary.json`
- `glow/pulse_trust/epoch_state.json`
- `glow/federation/quorum_status.json`
- `glow/governor/rollup.json`

These are correlated by host ID, node ID, scenario, topology, and seed.

## Outside current scope

- unbounded soak tests
- internet-scale autonomous multi-region operations
- implicit privileged orchestration outside declared transport model
