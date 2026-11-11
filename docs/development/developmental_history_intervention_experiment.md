# Developmental-history intervention experiment

This is the first preregistered resident developmental-history intervention. It
is an observational instrument, not a learning, improvement, identity,
selfhood, consciousness, sentience, or causal-closure claim.

Before inference, the owner validates the World-State snapshot and creates a
bounded `CurrentWorldStateCognitiveProjection`. Allowed source kinds are sorted
by source kind, source ID, and fact ID and capped by the configured exact fact
bound. The projection binds the exact fact payloads, source identity and
provenance, applicable conflicts, snapshot identity, selection-policy identity,
and its own content identity. It is read-only evidence—not truth, authority,
policy, a goal, or canonical explicit-user retention. This current-context
selection deliberately ignores the processed-evidence ledger; the separate
writeback selection still excludes exact evidence identities already processed.

When comparison is enabled and prior history exists, an immutable
history-intervention protocol is atomically persisted before the first model
invocation. Existing protocol versions preserve the fixed order:
history_present, history_withheld, history_restored. The opt-in companion
intervention also supports protocol v7 for explicitly selected order and
protocol v8 for a caller-supplied trial index. The owner derives the order for
v8, records the index, and verifies that the recorded order matches the
deterministic alternating schedule: even trials use history_present first;
odd trials use history_withheld first. This is counterbalancing, not
randomization. Restored remains third so it always follows
exact-history revalidation. The protocol binds the snapshot and current
projection, exact fact and developmental-record identities, record-set digest,
model/artifact/active identity, authority-map digest, fixed budget,
temperature-zero posture, template digest, comparisons, non-claims, and exact
invocation order. Persisted condition, score, and decision arrays remain in
canonical present/withheld/restored order for compatibility.

The maintained rootless Hermes cycle accepts the optional
`SENTIENTOS_HERMES_HISTORY_ORDER_TRIAL_INDEX` environment variable and passes
that validated index to both later companion-history comparisons. It records the
selected index in its cycle result and the experiment protocols. To counterbalance
independent invocations, the experiment supervisor must assign successive trial
indices; the one-shot runner does not allocate or persist a shared schedule.
When the variable is unset, the runner preserves the historical fixed order.

Withholding changes only the ephemeral prompt projection. It never deletes,
tombs, rewrites, or reclassifies history. Restoration re-reads every exact
record from the immutable developmental store and verifies its preregistered
digest before projecting it. Missing or changed retained state is therefore not
reported as deliberate withholding. Protocol and completed run artifacts live
under `state_root/developmental_experiments/{protocols,runs}`, separate from
developmental-history records/receipts and canonical user memory.

All three requests use the cognition-only governed purpose
`resident_developmental_history_intervention_experiment`, the same current
projection/template/budget/model/artifact/authority map and temperature zero;
temperature zero is not a hardware-determinism guarantee. Outputs remain
digest-only in durable receipts. The summary compares present-vs-withheld and
restored-vs-withheld and may report no observable difference, a stable
history-presence-associated difference, history-restoration instability, or a
mixed observation. A single trial does not identify an order effect. The
deterministic counterbalanced schedule helps expose positional confounding
across matched
trials, but does not randomize nuisance variables or by itself support a causal
order-effect estimate. These are bounded associations only.

For a structured objective task whose descriptor explicitly requires task-family history, the resident owner projects only exact, score-bound examples from the requested family that also match the active cognitive-model identity. The record-level natural-language interpretation is omitted from that task-specific prompt, and its separate digest is not sent to the model. The enclosing record and candidate digests continue to bind the omitted source content for audit. Unrelated selected facts and embodiment/security projections are not carried into that scoped packet. Included examples retain their evaluator correctness flags, so an incorrect example remains evidence of an incorrect outcome rather than being silently promoted to a lesson. The stored record and ordinary history remain unchanged.

This is a prompt-projection constraint, not a new memory owner, general truth filter, or cross-model transfer rule. The v3 Hermes transfer family exercises the scoped path; its synthetic results are mixed and do not establish reliable transfer or improved performance.

The broader capability remains `partial`. The separate controlled
[model-replacement experiment](developmental_model_replacement_experiment.md)
now holds this current/history condition fixed across two pre-governed cognitive
endpoints; it does not alter this intervention or production serving. Deferred
work includes repeated long-duration production trials, statistical inference,
real resident activation/serving transitions and cross-model cadence,
endogenous relevance, consequence learning, self-model
mutation, broad belief revision, forgetting policy, and resource-allocation
learning.
