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

For companion-decision runs, the verified run projection now carries each
condition's response digest, normalized and model disposition, and exact
current-evidence and history citations into the ordinary World-State/writeback
path. The writeback interpretation projection preserves this text-free contrast
for later cognition to evaluate. This records which condition produced which
proposal identity and citations; it does not mark the proposal correct, executed,
or improved, and it does not establish that later cognition applied the result
successfully.

Later context assembly exposes this contrast only when the current serving
identity matches the experiment's verified identity digest. The protocol keeps
the full identity and receipt lineage; the compact writeback fact keeps the
identity digest to stay within the existing evidence-size budget. Present and
restored history packets can therefore carry the comparison for that same
serving identity, while the matched withheld packet carries no history. This
is still an experimental proposal contrast: it establishes neither correctness,
cross-model transfer, execution, nor improved decisions.

The later prompt adds a compact `decision_pattern` derived from the three
response digests, dispositions, and history citations. Its
`proposal_fingerprint_relation` distinguishes a difference reproduced after
restoration, no observed response/disposition difference, and an unstable
restoration. Citation-only differences do not count as proposal differences.
The prompt keeps response digests opaque and warns that even a restoration-stable
difference does not identify the better proposal. A deterministic fake-inference
counterfactual consumes that relation in matching present/restored prompts and
changes its disposition; controls with no proposal difference or unstable
restoration do not trigger the same response. The withheld prompt has neither
the cue nor its citation. This verifies calibrated context-to-inference
behavior with a deterministic substitute, not whether a real model will
interpret the pattern correctly or make better decisions.

For a structured objective task whose descriptor explicitly requires task-family history, the resident owner projects exact, score-bound examples from the requested family with their source-model applicability posture. The record-level natural-language interpretation is omitted from that task-specific prompt, and its separate digest is not sent to the model. The enclosing record and candidate digests continue to bind the omitted source content for audit. Unrelated selected facts and embodiment/security projections are not carried into that scoped packet. Evaluator-correct examples are the only positive mapping evidence. Evaluator-incorrect examples are passed in a separate `prior_incorrect_examples` block explicitly labeled as historical errors, not mapping evidence, current truth, or authority; unknown-correctness rows remain withheld and represented by digest-only omission evidence. The task prompt tells the model not to repeat a failed answer for the same input. The durable record and ordinary history remain unchanged.

Outcome posture affects retrieval priority only when the restored score matches the history-present score. A favorable present-vs-withheld contrast with failed restoration is ranked as tentative history, below restoration-stable favorable evidence. Exact evaluator-correct examples remain available with their source and uncertainty qualifiers; the unstable comparison does not establish a repeatable history effect.

When eligible examples are spread across runs and no single contributing run
contains three distinct inputs, the prompt builder can fit a provisional
integer-affine relation across at least two distinct score-bound runs, each
contributing a distinct probe input, outside known unsettled task/model outcome
groups in the same declared family. It requires a one-to-one binding between
run IDs and run digests and one task, score, and source-model binding per run.
It deduplicates repeated probe inputs, rejects conflicting answers, excludes
adverse or unsettled source-outcome groups, and binds the
summary to the contributing run, score, record, and source-model digests. The
aggregation step recomputes each bound source-model digest from its retained
identity before counting it; sources without a verified identity remain
unbound. It also requires all contributing examples to have the same target
model identity, and checks each `same` or `different` applicability label
against the bound source and target digests. The prompt-bound summary includes
each run's distinct-input count and a digest of those counts, plus the number
and source counts of bound model
identities and unbound model sources. These summaries make the cross-run
qualification and source-model coverage auditable. The prompt instruction
treats model-identity counts and the target identity digest as provenance, not
independent trials or added evidence weight. The relation remains historical
guidance: neither learning nor cross-model performance transfer is established.
The projection digest records whether this accumulated candidate was included
in each history-present/restored prompt;
real-model use and transfer remain unverified.

Within equal outcome posture and model applicability, retrieval ranks exact
overlap with the current task's probe inputs before the number of distinct
usable probe inputs in a record. Repeated rows for the same input no longer
inflate its coverage tie-breaker; distinct evaluator-scored examples remain
available as evidence, and exact-probe overlap still wins first. The v8 and v3
policy identities record the revised family-ranking rule while earlier policy
identities remain accepted for persisted history. This controls which history
is surfaced, but does not show that a model learned from or applied it. The
controlled fixture verifies selection under the record cap, not that a model
will apply the retrieved answer correctly.

Retrieval gives an additional priority to a favorable result only when at least
two distinct admitted run IDs share the exact task commitment and source model
identity, and every available comparable run in that group is restoration-stable
and favorable. Repeated references to one run do not count twice; an unstable,
neutral, or adverse comparable run prevents this corroboration priority. This
selection rule helps later context distinguish a one-run outcome from a
repeat-run-consistent one. It does not establish statistical independence,
causality, general learning, or improved performance.

When comparable repeated outcomes for the same exact task and source model are
mixed, internally inconsistent, or include an unstable comparison, none of
their records receives the ordinary favorable or neutral outcome-ranking
priority. Their evaluator-scored examples and provenance remain available as
tentative history. Unrelated task commitments and source models are ranked
independently.

Score-bound incorrect examples now contribute task-family retrieval utility
even when a record has no evaluator-correct examples. This keeps an adverse,
error-only experience eligible for a bounded later prompt when its probes
overlap, while its lowest outcome priority keeps it behind positive or stable
neutral guidance. The examples remain historical negative context, not a
replacement mapping rule. A CPU-only controlled retrieval fixture demonstrates
that such a selected record reaches the bounded prompt projection; real-model
application and subsequent performance effects remain unverified.

New task-family trials use the v4 selective-answer contract. Each probe accepts
an integer answer or `null` abstention; evaluator correctness and abstention
are recorded separately, with coverage and accuracy among answered probes
reported independently. New score records use
`sentientos.objective_task_score:v5`: when any probe is unanswered, the
aggregate status is `selective` and aggregate correctness is unknown. Per-probe
correctness and exact correct-answer counts remain scoreable, so history
comparison can measure correct answers without counting abstentions as wrong.
Recovered v4 score records retain their historical aggregate semantics.
Abstentions have unknown evaluator correctness, so they are never positive
mapping guidance or negative answer feedback. A
score-bound v4 abstention is retained separately as a historical decision with
unknown correctness and no recorded reason. It can make a same-family record
retrievable for an overlapping probe at zero outcome priority, and appears in a
separate `prior_abstained_examples` prompt block. The task prompt instructs
the model not to treat it as mapping evidence or an instruction to abstain
again.
Unclassified unknown rows, including legacy v3 rows, remain withheld with
digest-only omission evidence. The history-conditioned prompt asks for
abstention until at least two distinct evaluator-correct inputs support the
mapping. Historical v3 task descriptors and scores remain readable with their
original integer-only contract. CPU-only controlled fixtures validate the
decision-history path and its score limits; they do not demonstrate that a
real model will use an abstention appropriately, abstain for a well-founded
reason, or apply the learned mapping.

When a bounded history selection includes a run from such a group, the
read-only retrieval projection also carries the exact-task, source-model, and
run-reference summary into the task-family prompt. This keeps the reason for a
record's higher retrieval priority visible when only one episode fits. The
history-withheld control omits this summary along with the history itself. The
summary is derived context only and remains explicitly non-authoritative.

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
