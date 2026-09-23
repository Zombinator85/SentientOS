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
writing one immutable `sentientos.developmental_model_replacement_campaign_report:v1`.
The report contains exact classification and comparison counts, per-condition ordered
output digests and diversity, restoration stability, and bounded all-trial booleans.
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
