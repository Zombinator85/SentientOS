# Rehearsal Playbook

The rehearsal flow exercises the hardened autonomy pipeline end-to-end. Run `make rehearse` locally or in CI to execute a dry
run. The command performs the following steps:

1. Seeds the runtime using `determinism.seed`/`SENTIENTOS_SEED`.
2. Invokes `sosctl rehearse --cycles 2`.
3. Stores artefacts in `glow/rehearsal/latest/`.

## Artefacts

| File | Description |
| --- | --- |
| `REHEARSAL_REPORT.json` | Summary of the run including oracle mode, critic disagreements, and module health. Payloads are signed with an ASCII-armoured digest. |
| `INTEGRITY_SUMMARY.json` | Peer review outcomes and quorum status; also signed. |
| `metrics.snap` | JSON snapshot of counters, gauges, and latency samples. |
| `logs/runtime.jsonl` | Correlation-aware JSON log for each rehearsal cycle. |

## Validating Results

- `oracle_mode` should read `online`. A value of `degraded` requires operator review.
- When critic disagreements occur they must be accompanied by a peer review entry and a council vote marked as deferred or tied.
- `/admin/status` reflects the same module summary, enabling external monitoring.

## CI Integration

Add the following steps to continuous integration workflows:

```bash
make rehearse
make audit
pytest -q
```

CI is considered green when the rehearsal artefacts exist, the audit succeeds, and unit tests pass. The signed artefacts in
`glow/rehearsal/latest/` provide provenance for release notes and compliance exports.
