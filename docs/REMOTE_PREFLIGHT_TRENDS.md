# Remote Preflight Trend Observatory

Remote preflight events are accumulated under:

- `glow/lab/remote_preflight/remote_preflight_history.jsonl` (bounded append-only window)
- `glow/lab/remote_preflight/remote_preflight_rollup.json`
- `glow/lab/remote_preflight/remote_preflight_trend_report.json`

## CLI surface

```bash
python -m sentientos.ops lab federation --remote-preflight-report --json
make remote-preflight-report
```

## Classification model

WAN/remote output now distinguishes:

- `remote_environment_drift_or_provisioning_failure`
- `remote_transport_or_auth_failure`
- `scenario_or_runtime_regression`
- `truth_or_gate_contradiction_failure`
- optional evidence sparsity remains in contradiction-policy/evidence-density artifacts as non-blocking when policy says so

Per-host preflight rows track classifications and labels such as:

- `host_unreachable`
- `transport_auth_failure`
- `command_availability_failure`
- `runtime_root_provisioning_failure`
- `cleanup_failure`
- `preflight_success`

## Operator triage flow

1. Check preflight trend report first. If transport/auth/provisioning errors trend up, treat as environment drift.
2. If preflight is healthy and scenario fails, inspect WAN scenario output and node evidence summaries.
3. If contradiction policy reports warning/blocking, treat as truth/gate contradiction path.
4. If evidence is sparse but non-blocking, continue with explicit caution and gather additional evidence.
