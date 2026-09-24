# Production developmental-model-replacement trial composition

`DevelopmentalModelReplacementProductionTrialRunner` is an explicitly invoked,
one-shot composition. It reconstructs an exact persisted campaign before model load,
determines its next preregistered trial, verifies exact hardened commissioned A/B
identities and two distinct externally supplied serving approvals, establishes A then
B, calls the campaign's existing one-trial transition once, closes B then A, writes an
immutable orchestration receipt, and stops. It contains no loop, retry, timer,
scheduler, daemon, background mode, or authority grant. A later trial requires a new
operator invocation and a newly reconstructed runner.

The receipt schema is
`sentientos.developmental_model_replacement_production_trial_receipt:v1`. It binds
campaign, base protocol, causal context, next trial, commissioned identities and
receipts, both serving lifetimes and `MODEL_SERVING` admission references, all five
inference receipt identities (each produced through normal independent
`LOCAL_MODEL_INFERENCE` admission), the resulting run and updated campaign state,
both closure receipts, invocation correlation, and evidence posture. It stores no raw
prompt or model output.

`production_experimental_trial` is permitted only with non-synthetic hardened
commissioning, non-synthetic approvals, the exact runtime worker factory, and the
production controller posture. Any enabled test seam or synthetic input can produce
only `synthetic_test_trial`; requesting production posture then fails closed.

Canonical activation bytes and canonical production-serving state bytes (including
exact absence) are snapshotted before and after the trial and must match. The frozen
developmental-history record-set digest must also match. Cleanup does not restore an
interrupted campaign: once the campaign marks a trial in progress, partial inference
failure leaves existing no-retry invalidation semantics intact while both workers are
still unloaded in B-then-A order. The runner never activates either experimental
model, changes production serving, changes developmental history, or transitions the
resident default cognitive model.

This is bounded production experimental evidence, not evidence that model B is
better, repeated production evidence, learning, persistent identity, selfhood,
sentience, consciousness, or causal closure.
