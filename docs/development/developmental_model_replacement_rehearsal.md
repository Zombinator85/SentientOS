# Developmental model-replacement system rehearsal

This repository-native instrument exercises the real experiment, repeated campaign,
experimental-serving controller, governed local-model inference, one-shot production
trial composition, durable reconstruction, and aggregation owners. It produces only
`synthetic_test_trial` evidence. It is not production experimental evidence and does
not prove that real model bytes were executed.

Run each bounded action as a separate process against an empty, caller-selected root:

```bash
PYTHONPATH=. python scripts/run_developmental_model_replacement_rehearsal.py prepare --root /tmp/model-replacement-rehearsal --summary
PYTHONPATH=. python scripts/run_developmental_model_replacement_rehearsal.py verify --root /tmp/model-replacement-rehearsal --summary
PYTHONPATH=. python scripts/run_developmental_model_replacement_rehearsal.py run-next --root /tmp/model-replacement-rehearsal --summary
PYTHONPATH=. python scripts/run_developmental_model_replacement_rehearsal.py verify --root /tmp/model-replacement-rehearsal --summary
PYTHONPATH=. python scripts/run_developmental_model_replacement_rehearsal.py run-next --root /tmp/model-replacement-rehearsal --summary
PYTHONPATH=. python scripts/run_developmental_model_replacement_rehearsal.py summarize --root /tmp/model-replacement-rehearsal --summary
PYTHONPATH=. python scripts/run_developmental_model_replacement_rehearsal.py verify --root /tmp/model-replacement-rehearsal --summary
```

`prepare` performs zero trials. Each `run-next` reconstructs disk state and performs
exactly one preregistered trial. `verify` and `summarize` perform no serving load or
inference. There is deliberately no repeat, all, watch, or daemon option.

The bundle's scenario uses
`sentientos.developmental_model_replacement_rehearsal:v1`; digest-bound verification
receipts use
`sentientos.developmental_model_replacement_rehearsal_verification:v1`. The manifest
binds context, history, protocol, campaign, commissioned evidence, A/B identities,
canonical sentinels, and the exact two-trial inventory. Verification binds campaign
state, trial/run/serving/closure/inference receipts and preservation results.

Synthetic commissioning receipts are created only inside this explicitly named
rehearsal module, in an isolated authenticated test installation, from real tiny local
fixture bytes and an authoritatively deployed synthetic catalog. The normal
`verify_commissioned_model()` consumer still checks hardened receipt, catalog, artifact,
authority-map, and identity custody with its explicit `allow_synthetic_for_tests` seam.
Production verification defaults and schemas are not changed.

Fault preparation accepts `--fault model_b_load_failure`, `loaded_identity_drift`, or
`inference_currentness_failure`. Protocol and campaign tamper cases are exercised by
the E2E suite. Failures retain the campaign's existing no-retry behavior.

A human does not have to manually execute the rehearsal during a Codex task. A Codex
agent may and should execute this rehearsal as part of relevant future
developmental/model-replacement work. It is safe for ordinary isolated agent
workspaces only within these boundaries: synthetic commissioning evidence,
deterministic fake workers, isolated installation custody, no provider/network/model
acquisition, and no canonical real-world production state.

> Run the developmental model-replacement system rehearsal before modifying the
> model-replacement, experimental-serving, campaign, or production-trial chain. Repair
> task-caused rehearsal regressions before landing.
