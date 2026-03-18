# Remote Smoke CI Lane (Ephemeral SSH, bounded)

This lane is **optional** and non-default. It continuously validates true remote-host smoke transport without changing normal CI cost.

## Workflow

- Workflow: `.github/workflows/remote-smoke-ci.yml`
- Trigger: `workflow_dispatch` or daily schedule.
- Bounds:
  - topology: `two_host_pair`
  - nodes-per-host: `1`
  - runtime: `1.8s`
  - deterministic seed: `11`
  - bounded scenario set: one selected smoke alias (`remote_partition_recovery_smoke`, `remote_epoch_rotation_smoke`, `remote_reanchor_truth_smoke`)

## Secrets and inventory

Template inventory is checked in at `.github/remote-smoke/hosts.ephemeral.yaml`.
`python scripts/render_remote_smoke_inventory.py` renders a runtime inventory using:

- `REMOTE_SMOKE_HOST_1`
- `REMOTE_SMOKE_HOST_2`
- `REMOTE_SMOKE_USER`
- `REMOTE_SMOKE_RUNTIME_ROOT`

The workflow only runs when these secrets exist.

## Canonical invocations

```bash
make federation-wan-remote-smoke-ci HOSTS=.github/remote-smoke/hosts.rendered.yaml
python -m sentientos.ops lab federation --wan --remote-smoke --hosts .github/remote-smoke/hosts.rendered.yaml --scenario remote_partition_recovery_smoke --topology two_host_pair --seed 11 --runtime-s 1.8 --nodes-per-host 1 --json
python -m sentientos.ops lab federation --wan-gate --remote-smoke --hosts .github/remote-smoke/hosts.rendered.yaml --scenario remote_partition_recovery_smoke --topology two_host_pair --seed 11 --runtime-s 1.8 --nodes-per-host 1 --json
```

## What this lane proves / does not prove

It proves the bounded remote SSH dispatch + preflight + collection path is still operational.
It does **not** replace full operator-driven WAN campaigns or exhaustive remote topology coverage.
