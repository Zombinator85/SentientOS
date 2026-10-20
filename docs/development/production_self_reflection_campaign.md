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

PYTHONPATH=. python scripts/run_production_self_reflection_campaign.py status \
  --campaign-root "$SENTIENTOS_DATA_ROOT/experiments/production-self-reflection/CAMPAIGN"

PYTHONPATH=. python scripts/run_production_self_reflection_campaign.py report \
  --campaign-root "$SENTIENTOS_DATA_ROOT/experiments/production-self-reflection/CAMPAIGN"
```

The standalone CLI deliberately has no `run-one` path. A JSON bundle can carry
digests and identifiers but cannot establish that canonical transition,
activation, serving, inference, or developmental-history owners issued them.
Passing a caller-constructed bundle to the campaign executor would therefore
mistake integrity for provenance. A future live campaign composition must
invoke the existing in-process owner verifiers and pass their verified results
to the campaign; it must preserve the exact operator and subordinate approval
rails. Immutable protocols, readiness artifacts, receipts, failures, and the
final report live below the campaign root. Expected fail-closed states include specific missing A/B,
commissioning, approval, transition, self-model/history, backend, interrupted,
canonical-conflict, and synthetic-component classifications. An in-progress
trial discovered after process death is terminal and is never silently retried.

Calling `create` again for the same campaign root verifies the exact immutable
protocol, the digest-bound state, ordered completed-trial identities, and every
referenced receipt before returning the existing campaign. It preserves partial
and completed progress. Missing or mismatched protocol/state/receipt custody
fails closed; an in-progress trial is marked interrupted and cannot be retried.
Before a later trial starts or a completed report is emitted, the campaign
rechecks the full ordered completion prefix and every referenced receipt. A
missing, replaced, reordered, or tampered earlier receipt therefore blocks both
continued execution and reporting; the executor is not called and no report is
written when that lineage fails verification.
Report scoring consumes the receipt mappings returned by that verification
pass. It does not reopen receipt paths after custody validation, so a later
on-disk replacement cannot change the outcomes summarized by that report.
For new protocols with verified transition-stage receipts, the descriptive
report also includes the exact campaign protocol digest and a compact per-trial
provenance inventory. Each row binds its trial ID and immutable receipt digest
to the verified transition binding digest, transition protocol identity, phase
order, and stage count. It omits operator
authentication details and grants no execution or scoring authority. Reports
with verified trial provenance use report schema v2; reports from historical v1
receipts retain their v1 schema and prior field set.
An already-published report from before the provenance inventory was added is
returned unchanged when it exactly matches the currently revalidated receipt
lineage; immutable report bytes are never upgraded in place.
The durable campaign owner uses a private POSIX interprocess lock while it
claims and executes a trial, updates progress, reconstructs interrupted state,
and emits a report. Concurrent owners therefore cannot execute the same trial
or misclassify a live in-progress trial as a process interruption. Platforms
without the repository's native `flock` custody fail closed for these campaign
operations.
Before executing, `run_one` also verifies the readiness receipt schema, digest,
and exact protocol identity against the campaign. A ready receipt must show all
readiness checks true, production evidence posture, no synthetic components,
and no authority or effect claim. A not-ready receipt remains a blocked result.
This digest is an integrity binding, not a signature or independent proof of
the observations supplied to the readiness verifier; live operation remains
subject to the existing executor and approval rails.


## Read-only live transition binding

`ProductionSelfReflectionTransitionBindingObserver` checks the durable
campaign's exact installation, transition protocol, and journal identity
against the already-composed in-process
`LiveTransitionOperatorRuntime`. It verifies campaign progress and inspects
operator request custody while holding a nonblocking campaign lock. Its output
is a binding report only: it does not process a request, advance a trial, grant
readiness, or authorize execution. A mismatched or interrupted transition
remains unverified. The daemon owner and subordinate owners remain responsible
for any later execution admission.

## Daemon observation

Set `SENTIENTOS_PRODUCTION_SELF_REFLECTION_CAMPAIGN_ROOT` to an absolute path
for an existing private campaign to include the read-only transition binding
in the daemon's operator-transition status. The daemon opens only existing
campaign files and verifies them under a nonblocking lock. A busy or invalid
campaign is reported as unverified. The daemon does not initialize or recover
campaign state, submit operator requests, advance a trial, or grant readiness.
With the setting absent, it performs no campaign inspection.
