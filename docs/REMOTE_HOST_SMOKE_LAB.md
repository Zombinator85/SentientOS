# Remote Host Smoke Lab

This runbook defines the bounded true remote-host smoke lane for WAN federation validation.

## Purpose

This lane verifies that the existing WAN federation + truth oracle + contradiction policy + WAN release gate stack can be exercised over declared remote hosts using the existing transport abstraction.

It is optional and non-default.

## What it runs

Remote smoke scenario aliases:

- `remote_partition_recovery_smoke` -> `wan_partition_recovery`
- `remote_epoch_rotation_smoke` -> `wan_epoch_rotation_under_partition`
- `remote_reanchor_truth_smoke` -> `wan_reanchor_truth_reconciliation`

Smoke bounds:

- single node per host
- capped runtime
- preselected scenario subset only

## Commands

Single remote smoke run:

```bash
python -m sentientos.ops lab federation --wan --hosts hosts.yaml --remote-smoke --scenario remote_partition_recovery_smoke --json
```

Remote gate run:

```bash
python -m sentientos.ops lab federation --wan-gate --hosts hosts.yaml --remote-smoke --json
```

Make target:

```bash
make federation-wan-remote-smoke HOSTS=hosts.yaml
```

## Remote preflight/bootstrap

Each SSH host is preflighted before dispatch:

- command availability checks (`sh`, `mkdir`)
- runtime root creation check
- explicit preflight status classification in `remote_preflight_report.json`

Preflight failures are represented as provisioning failures in the preflight artifact and dispatch log.

## Artifact collection

For SSH hosts, bounded remote collection captures per-node dispatch artifacts into local run root:

- `remote_collected/<host>/nodes/<node>/glow/lab/remote_dispatch_collected.json`
- `remote_artifact_collection.json`
- `remote_dispatch_log.jsonl`
- merged `artifact_hash_manifest.json`

All files remain in the existing WAN run folder and flow through existing truth/gate outputs.

## Failure interpretation

- Preflight failure: remote environment/provisioning issue.
- Scenario failure with successful preflight: WAN scenario/truth contradiction behavior issue.
- Gate failure: contradiction policy blocked promotion for the scenario set.

## Out of scope

This smoke lane does **not** prove:

- long-haul WAN soak resilience
- internet-scale federation behavior
- high-cardinality remote host scheduling
- full production rollout readiness by itself
