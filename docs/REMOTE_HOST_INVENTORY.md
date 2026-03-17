# Remote Host Inventory

The remote smoke lane uses the existing `--hosts` option on `python -m sentientos.ops lab federation`.

## Supported formats

- JSON (`.json`)
- YAML (`.yaml` / `.yml`)

## Canonical schema

```yaml
hosts:
  - host_id: host-01
    address: 10.0.0.11
    user: sentientos
    transport: ssh
    runtime_root: /var/tmp/sentientos-wan
    zone: us-east-1a
    fault_domain: rack-a
    latency_class: wan
    tags: [smoke,canary]
    capabilities: [python3,ssh]
```

Required fields per host:

- `host_id`
- `transport`
- `runtime_root`

Optional fields:

- `address`
- `user`
- `zone`
- `fault_domain`
- `latency_class`
- `tags`
- `capabilities`

Notes:

- `host_id` values must be unique.
- Host rows are normalized and sorted by `host_id` for deterministic run metadata.
- `transport` may be `local`, `mock`, or `ssh`.
