# Production self-reflection campaign

## Capability and boundary

**ESTABLISHED:** SentientOS has an operator-invoked, fail-closed campaign
composition for controlled `self_model_present -> self_model_withheld ->
self_model_restored` assessment across the canonical live resident A→B→A phase
order. The immutable protocol binds installation, model commissioning and
provenance, persistent state, assessment/scorer, transition custody, and a 2–32
trial no-retry policy. Readiness is derived from observed components and grants
no authority.

**NOT ESTABLISHED merely by this code:** that a production trial occurred; that
self-model access helps; that B preserves anything psychologically meaningful;
that restored A has personal continuity; that development or recursive
improvement occurred; or consciousness or sentience.

The campaign composes existing owners. It does not issue activation, serving,
inference, or transition approvals, and it does not replace commissioning,
stable-slot serving, transition journaling, World-State, longitudinal
reconciliation, developmental history, or the external deterministic scorer.
Any component not mechanically observed as `nonsynthetic` makes requested
production posture fail closed.

## Operator package

Prepare an exact JSON configuration containing the fields accepted by
`ProductionSelfReflectionProtocol.create`, including commissioned A/B receipt
bindings, exact artifact identities, approval identities, inference-authority
maps, state/reconciliation boundaries, assessment key/scorer digests, and the
installed live transition protocol. No aliases (`latest`, `current`, `default`,
or `*`) are accepted.

```bash
PYTHONPATH=. python scripts/run_production_self_reflection_campaign.py create \
  --campaign-root "$SENTIENTOS_DATA_ROOT/experiments/production-self-reflection/CAMPAIGN" \
  --config /operator/custody/production-self-reflection-protocol.json

PYTHONPATH=. python scripts/run_production_self_reflection_campaign.py readiness \
  --campaign-root "$SENTIENTOS_DATA_ROOT/experiments/production-self-reflection/CAMPAIGN" \
  --observed /operator/custody/current-production-observations.json \
  --readiness-output "$SENTIENTOS_DATA_ROOT/experiments/production-self-reflection/CAMPAIGN/readiness/READINESS.json"

PYTHONPATH=. python scripts/run_production_self_reflection_campaign.py run-one \
  --campaign-root "$SENTIENTOS_DATA_ROOT/experiments/production-self-reflection/CAMPAIGN" \
  --observed /operator/custody/current-production-observations.json \
  --evidence-bundle /operator/custody/live-sentientosd-one-trial-evidence.json

PYTHONPATH=. python scripts/run_production_self_reflection_campaign.py status \
  --campaign-root "$SENTIENTOS_DATA_ROOT/experiments/production-self-reflection/CAMPAIGN"

PYTHONPATH=. python scripts/run_production_self_reflection_campaign.py report \
  --campaign-root "$SENTIENTOS_DATA_ROOT/experiments/production-self-reflection/CAMPAIGN"
```

The evidence bundle must be emitted by the real live `sentientosd` transition
composition after its exact operator requests and subordinate approvals; it is
not an approval and cannot cause an unauthorized stage. Immutable protocols,
readiness artifacts, receipts, failures, and the final report live below the
campaign root. Expected fail-closed states include specific missing A/B,
commissioning, approval, transition, self-model/history, backend, interrupted,
canonical-conflict, and synthetic-component classifications. An in-progress
trial discovered after process death is terminal and is never silently retried.
