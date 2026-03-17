# WAN Truth Oracle and Reconciliation

The WAN lab now supports a truth-oracle pass that evaluates runtime evidence across hosts instead of relying only on scenario intent.

## What it evaluates

For every WAN run, the oracle can derive explicit truth dimensions:

- `quorum_truth`
- `digest_truth`
- `epoch_truth`
- `replay_truth`
- `reanchor_truth`
- `fairness_truth`
- `cluster_health_truth`

Each dimension is classified as one of:

- `consistent`
- `degraded_but_explained`
- `inconsistent`
- `missing_evidence`
- `blocked_by_policy`

## Data sources

The oracle reads per-node and cluster evidence including:

- constitution summaries
- quorum status
- governance digest posture
- pulse trust epoch posture
- audit trust/re-anchor continuation evidence
- daemon runtime transition logs
- WAN fault timeline and executed faults
- replay verification outputs (`glow/forge/replay/replay_*.json`)

## Reconciliation model

The reconciliation layer aligns:

- host ids, node ids, scenario ids, topology ids, and seed
- deterministic fault schedule id from `fault_timeline.json`
- per-node replay artifacts to node identity
- checkpoint/re-anchor ids to participating nodes
- final cluster digest claim to recomputed digest from per-node final trust state

Outputs are written to deterministic JSON artifacts under `wan_truth/` in the run root.

## Operator usage

- `python -m sentientos.ops lab federation --wan --scenario wan_partition_recovery --truth-oracle --json`
- `python -m sentientos.ops lab federation --wan --truth-oracle --truth-report`
- `python -m sentientos.ops lab federation --wan --emit-replay --truth-oracle --json`

## Interpretation

The run now includes both:

- scenario oracle outcome (`expected` vs `observed`)
- evidence truth outcome (truth dimensions + provenance reconciliation)

Use contradictions report when these disagree.
