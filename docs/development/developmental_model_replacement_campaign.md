# Developmental model-replacement replication campaign

This instrument preregisters **2–32** explicit, ordered trial IDs over one immutable
`sentientos.developmental_model_replacement_campaign_protocol:v1`. The protocol binds
the base five-condition protocol and causal context; both exact model identities and
source-bound provenance manifests; history record-set and current-projection digests;
inference budget, generation posture, condition order, aggregation rules, and explicit
non-claims. It is persisted before trial one.

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
writing one immutable `sentientos.developmental_model_replacement_campaign_report:v3`.
The report contains exact classification and comparison counts, per-condition ordered
output digests and diversity, restoration stability, and bounded all-trial booleans.
For scored probe suites it also records each probe's condition-outcome counts and
cross-condition transitions across replications. Answered-probe totals exclude
invalid, unavailable, and truncated responses; those remain separately classified
from selective abstentions in the outcome counts. The report builder checks that
per-probe correct, answered, abstained, and transition counts reconcile with its
aggregate totals before publishing the immutable report.
After restart, `load_report(report_id, expected_report_digest=...)` first checks
the stored report digest and campaign identity, then rebuilds the report from
the campaign state and every verified trial artifact. A report is returned only
when the stored content exactly matches that reconstruction.
The loader also reconstructs historical v1 aggregate-only and v2 per-probe
reports using their original invalid-answer coverage semantics; new summaries
are written only as v3.
`world_state_records(report_refs=...)` projects only explicitly selected,
reverified campaign reports as digest-bound historical observations. It carries
their trial/run references, model/context identities, and bounded objective
outcomes; it does not write developmental history. Event time is included only
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

Campaign custody is under
`developmental_experiments/model_replacement_campaigns/{protocols,state,failures,reports}`.
It neither reads nor writes developmental history, canonical explicit-user retention,
production activation, or production serving state. This is repeated controlled
replication of one frozen context—not longitudinal development, learning, statistical
significance, a hypothesis probability, identity, selfhood, sentience, consciousness,
or causal closure. Synthetic tests are not production evidence. A real governed
resident A→B serving transition and restoration remains a separate later experiment.
