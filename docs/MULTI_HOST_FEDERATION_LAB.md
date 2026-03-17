# Multi-Host Federation Lab

SentientOS now includes an optional WAN/multi-host federation lab wing layered onto `python -m sentientos.ops lab federation`.

## What is new

- Explicit host inventory (`--hosts`) with host IDs, transport, runtime roots, zones, latency classes, and fault domains.
- Deterministic topology families via `--topology`:
  - `two_host_pair`
  - `three_host_ring`
  - `three_host_partial_mesh`
  - `fault_domain_split`
- Deterministic node-to-host placement from seed and topology.
- Per-host runtime roots and per-host lifecycle transition logs.
- Optional WAN suite mode (`--wan-suite`) and single-scenario WAN mode (`--wan`).
- Optional bounded true remote smoke lane (`--remote-smoke`) over declared hosts.

## Example commands

```bash
python -m sentientos.ops lab federation --wan --scenario wan_partition_recovery --topology three_host_ring --json
python -m sentientos.ops lab federation --wan --hosts hosts.json --scenario wan_asymmetric_loss --topology fault_domain_split --json
python -m sentientos.ops lab federation --wan-suite --topology three_host_partial_mesh --json
python -m sentientos.ops lab federation --wan --hosts hosts.yaml --remote-smoke --scenario remote_partition_recovery_smoke --json
python -m sentientos.ops lab federation --wan-gate --hosts hosts.yaml --remote-smoke --json
make federation-wan-remote-smoke HOSTS=hosts.yaml
make federation-lab-wan
```

## Host inventory format

Provide JSON via `--hosts`:

```json
{
  "hosts": [
    {
      "host_id": "host-01",
      "transport": "local",
      "runtime_root": "glow/lab/wan/host-01",
      "address": "",
      "user": "",
      "zone": "z1",
      "latency_class": "lan",
      "fault_domain": "fd-a"
    }
  ]
}
```

`transport` can be `local`, `mock`, or `ssh`.
