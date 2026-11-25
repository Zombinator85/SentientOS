# Developmental model-replacement replication campaign

This instrument preregisters **2–32** explicit, ordered trial IDs over one immutable
campaign protocol. Historical v1/v2 protocols retain their original fixed-order
interpretation; new campaigns use unscored v3 or scored v4 with a per-trial
counterbalanced condition schedule. The protocol binds
the base five-condition protocol and causal context; both exact model identities and
source-bound provenance manifests; history record-set and current-projection digests;
inference budget, generation posture, condition order, aggregation rules, and explicit
non-claims. It is persisted before trial one.

## Offline preregistration boundary

`DevelopmentalModelReplacementCampaign.create(...)` persists the frozen context,
model identities, provenance, campaign protocol, and empty initial state. It does
not call either inference endpoint or activate a model; the first model call is
inside an explicit `run_next_trial()` operation. This makes protocol preparation
possible while GPU-backed inference is paused, provided the caller already has
the exact governed endpoint identities and frozen context to bind. The API is
not a detached planning CLI: constructing a real experiment still requires those
bound inputs, and synthetic rehearsal identities must not be presented as real
model evidence. `inspect_custody(...)` can later verify a persisted campaign
without either endpoint.

Each explicit call to `run_next_trial()` first atomically records the next trial as in
progress. Trial identity enters run, observation, and correlation identity, but never
the semantic prompt, current evidence, history, provenance, budget, or generation
posture. The existing experiment still owns all five conditions and within-trial
classification. There is no scheduler, timer, daemon, background thread, retry, or
independent cadence.

State uses `sentientos.developmental_model_replacement_campaign_state:v1` and binds
completed trial/run IDs and digests, the next and in-progress trial, validity, and any
failure reason. Reconstruction continues only at the next preregistered trial. An
in-progress trial without completion is invalidated as
`campaign_interrupted_during_trial`; it is never replayed. Protocol, state, control,
model, provenance, or trial-artifact tampering fails closed.

A complete campaign rereads and digest-verifies every ordinary trial artifact before
writing one immutable `sentientos.developmental_model_replacement_campaign_report:v7`.
The report contains exact classification and comparison counts, per-condition ordered
output digests and diversity, restoration stability, and bounded all-trial booleans.
It also exposes each preregistered and observed trial order plus per-condition counts
at execution positions one through five. These are schedule-coverage data; the report
also binds each condition's output digest and bounded objective score counts to its
observed position. These are schedule-coverage and outcome records; the report does
not estimate or claim a position effect. Historical v1–v5 report schemas remain
reconstructible using their original payload shape.
For scored probe suites it also records each probe's condition-outcome counts and
cross-condition transitions across replications. Answered-probe totals exclude
invalid, unavailable, and truncated responses; those remain separately classified
from selective abstentions in the outcome counts. The report builder checks that
per-probe correct, answered, abstained, and transition counts reconcile with its
aggregate totals before publishing the immutable report. Objective summaries also
retain each trial's paired correctness, answer-coverage, and abstention deltas for
history-present versus withheld, model A versus B, and A restoration comparisons.
Each paired summary reports positive, negative, and zero trial counts alongside
the net delta sums, so opposing outcomes remain visible even when their net is zero.
Unscoreable pairs remain in the trial list with their statuses and null deltas, so
the aggregate cannot hide which repetitions contributed evidence.
Calibrated selective objective scores (schema v6) use the same independently
verified answered and abstained counts as selective v5 scores; confidence values
do not affect the campaign's correctness, answer-coverage, or abstention deltas.
Legacy score schema v4 keeps its original aggregate rule that any abstention
means `incorrect`, while campaign coverage and abstention totals use that score's
verified per-probe counts instead of treating it as fully answered.
Calibrated task-family schema v5 now enters the same per-probe aggregation and
represents a null answer as an abstention; confidence values remain excluded from
correctness and transition counts.
After restart, `load_report(report_id, expected_report_digest=...)` first checks
the stored report digest and campaign identity, then rebuilds the report from
the campaign state and every verified trial artifact. A report is returned only
when the stored content exactly matches that reconstruction.
When the original experiment object or its model endpoints are unavailable,
`verify_report_from_artifacts(artifact_root=..., experiment_state_root=...,
campaign_id=..., report_id=..., expected_report_digest=...)` performs the same
reconstruction from the persisted campaign protocol/state and experiment
protocol/context/objective-plan/run artifacts. It does not load, invoke, or require
either cognitive endpoint; endpoint independence here is a property of evidence
recovery, not evidence that cognition or developmental continuity survived model
replacement.
`world_state_records_from_artifacts(artifact_root=...,
experiment_state_root=..., campaign_id=..., report_refs=...)` uses that same
read-only reconstruction to emit the explicitly selected, reverified historical
World-State observations without requiring the original endpoint objects.
The loader also reconstructs historical v1 aggregate-only, v2 and v3 per-probe,
and v4 paired-delta reports using their original shape and invalid-answer
coverage semantics; new summaries are written only as v5.
`world_state_records(report_refs=...)` projects only explicitly selected,
reverified campaign reports as digest-bound historical observations. It carries
their trial/run references, model/context identities, and bounded objective
outcomes, records the source report's actual schema version, and does not write
developmental history. Event time is included only
when the underlying run projection verifies every condition receipt timestamp.
If even one trial run is ineligible for World-State projection, the campaign
projection fails closed rather than reintroducing its scores through the
aggregate report.
When present, the aggregate timestamp and each trial timestamp are also copied
into the payload, which World-State includes in its content digest even though
it excludes the top-level event-time field.
An operator must still add the returned records to the desired World-State
snapshot and pass them through ordinary history admission before any later
cognition can consume them.
Zero effects, A-only, B-only, both-model effects, output variation, and restoration
instability are valid descriptive outcomes.

## Condition-order counterbalancing

New campaign protocol v3 (unscored) and v4 (scored) bind a legal five-condition
execution order for every trial before any endpoint call. Existing v1/v2
campaign identities retain their original semantic payload and fixed-order
interpretation. The four schedules cross the order of A's history-present and
history-withheld conditions with the order of B's equivalent conditions;
restored A remains last. Two-trial campaigns use opposing schedules, three
trials use three distinct schedules, and larger campaigns cycle all four while
keeping assignment counts within one.

The experiment run records its actual execution order, journals each condition
by identity, and keeps completed observations canonicalized by condition for
scoring and aggregate comparisons. Read-only run verification follows the
recorded journal order and checks observation evidence by condition identity.
New condition-start v3 artifacts digest-bind the planned execution order and each
condition's one-based position, then link to the previous completed condition's
start digest. Run recovery and verification follow that chain, so new journals
can provide a digest-linked record of start order under the runner protocol. This
is not a trusted timestamp or externally authenticated, tamper-proof log; a writer
with artifact-store access could rebuild an unkeyed digest chain. Condition-start
v2 artifacts bind positions without a predecessor chain; v1 artifacts do not
bind order. Older counterbalanced runs remain readable from their run and
preregistered campaign records, and custody reports identify the weaker evidence
posture. This order evidence does not make the schedule randomized or establish a
causal effect.
World-State projections also validate and emit canonical condition order.
Campaign reports remain descriptive: counterbalancing reduces one order
confound, but does not establish learning, development, or durable improvement.
Report v7 carries each trial's order-evidence posture and bounded condition-start
witnesses into campaign World-State v3. Resident cognition can recompute the
start digests and predecessor links from that record instead of trusting the
posture label alone. Report v6 remains readable with its original run-level-only
posture. These artifacts preserve verified execution order and its evidence
limits for historical cognition. The report and compact writeback summary also
state that digest-chain verification is structural evidence, not external
authentication or trusted time.

Campaign custody is under
`developmental_experiments/model_replacement_campaigns/{protocols,state,failures,reports}`.
It neither reads nor writes developmental history, canonical explicit-user retention,
production activation, or production serving state. This is repeated controlled
replication of one frozen context—not longitudinal development, learning, statistical
significance, a hypothesis probability, identity, selfhood, sentience, consciousness,
or causal closure. Synthetic tests are not production evidence. A real governed
resident A→B serving transition and restoration remains a separate later experiment.
