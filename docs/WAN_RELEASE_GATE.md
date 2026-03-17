# WAN Release Gate

The WAN release gate is an explicit, optional operator command that runs bounded WAN scenarios, applies truth-oracle contradiction policy, and returns deterministic release outcomes.

## Canonical gate scenarios

- `wan_partition_recovery`
- `wan_asymmetric_loss`
- `wan_epoch_rotation_under_partition`
- `wan_reanchor_truth_reconciliation`

## CLI surface

Use the existing command surface:

```bash
python -m sentientos.ops lab federation --wan-gate --json
python -m sentientos.ops lab federation --wan-gate --scenario wan_partition_recovery --json
python -m sentientos.ops lab federation --wan-suite --truth-oracle --json
make federation-wan-gate
```

## Artifacts

The gate writes bounded artifacts to `glow/lab/wan_gate/`:

- `wan_gate_report.json`
- `scenario_gate_results.json`
- `contradiction_policy_report.json`
- `release_gate_manifest.json`
- `final_wan_gate_digest.json`
- `scenario_evidence_completeness.json`
- `evidence_density_report.json`

These artifacts answer:

- what scenarios ran
- what contradictions were observed
- which contradictions were tolerated/warned/blocked
- why the aggregate gate passed or failed
- which scenarios were default-complete / fully-evidenced
- whether degradation is evidence-sparse vs contradiction-driven

## Triage guidance

1. Check `wan_gate_report.json` for aggregate outcome and per-scenario failure causes.
2. For blocking cases, inspect each scenario's `policy.records` and linked `truth_oracle` artifacts.
3. For warning/indeterminate, inspect missing evidence counts and determine whether rerun or environment correction is required.
4. Keep baseline simulation and protected corridor checks separate: WAN gate is release-grade multi-host contradiction validation, not a replacement.
