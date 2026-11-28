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
invocation. Unscheduled legacy protocols preserve the fixed order:
history_present, history_withheld, history_restored. The opt-in companion
intervention also supports protocol v7 for explicitly selected order and
protocol v8 for the legacy alternating-first trial index. Objective task
comparisons use protocol v9 for that same legacy schedule. New scheduled
companion and objective comparisons use protocol v10 and v11 respectively.
They bind the task/history selection, trial index, and one of all six condition
permutations. Over each six-trial block, every condition appears twice in every
position. Exact retained history is revalidated immediately before the
restored-condition invocation, so restored need not always occupy the final
position. This deterministic balance is counterbalancing, not randomization.
The resident owner allocates the next index under its tick lock and persists a
protocol-bound schedule claim before the first condition inference. An explicit
index override is accepted only when it is the next slot for the exact matched
task/model/context. Older v8/v9 artifacts retain their alternating-first
and restoration-third interpretation. Unscheduled objective comparisons use
protocol v12: it keeps the fixed legacy order and persists per-probe correctness
and answerability transitions for scored suites in `objective_evaluation`.
Answerability is reported separately so a history-associated change between
answering and abstaining is measurable even when correctness for that probe is
unknown. Restoration comparisons likewise report correctness and answerability
stability independently. The `gain`/`cost` transition labels indicate only
whether history increased or decreased answerability; they do not rank
answering above abstaining or prescribe which behavior the system should adopt.
Recovery recomputes these transitions from the
independently verified score rows and rejects a mismatch. Recovery also accepts
the earlier immutable run-summary shape after independently recomputing its
correctness-only transitions and original selective-score assessment posture,
and the intermediate answerability-summary shape, so the new fields and
scoreability fix do not invalidate already-recorded evidence. Legacy v2 affine
suites have no retained per-probe rows, so recovery derives only each probe's
correctness from the verified answer list and frozen task plan; answer values
are not copied into the transition summary. The protocol binds the snapshot and current
projection, exact fact and developmental-record identities, record-set digest,
model/artifact/active identity, authority-map digest, fixed budget,
temperature-zero posture, template digest, comparisons, non-claims, and exact
invocation order. Persisted condition, score, and decision arrays remain in
canonical present/withheld/restored order for compatibility.

Calibrated selective family-suite tasks use objective protocol v13. It retains
the balanced six-permutation schedule and per-probe correctness and
answerability transitions while requiring the v5 family task contract to be
bound in the immutable pre-inference task plan. The contract records a
confidence value for each answered prediction; score v6 checks those values
against the independent oracle and records squared probability error. The
objective summary reports per-condition Brier sums, scored-answer counts, and
descriptive means. These metrics describe this preregistered task only: a Brier
score is not proof of calibration, history-caused improvement, or transferable
learning. Protocols v11 and v12 and family-suite v4 retain their prior
contracts.

An objective schedule slot is reserved when its immutable protocol and claim
are persisted, before condition inference. A later crash does not free that
slot: fully receipted conditions can be recovered into the original run without
replaying inference, while an incomplete run remains incomplete and the next
request for the same exact binding receives the next index. Consequently, a
six-run cohort requires six complete runs from one uninterrupted schedule
block; it cannot silently skip an interrupted index or combine trials across
blocks. Requests blocked before protocol creation do not consume a slot. This
distinguishes preregistered exposure from completed evidence and prevents
retries from reusing a condition order after partial exposure.

The maintained rootless Hermes cycle accepts the optional
`SENTIENTOS_HERMES_HISTORY_ORDER_TRIAL_INDEX` environment variable and passes
that validated index to objective acquisition and transfer condition order as
well as both later companion-history comparisons. When unset, the resident
owner allocates and persists the next objective index automatically. Balanced
objective protocols use v11, calibrated family-suite protocols use v13, and
companion protocols use v10 to bind their six-permutation order; score
and decision arrays remain in canonical
present/withheld/restored order for compatibility. The cycle records the
selected index in its result and experiment protocols. To counterbalance
matched independent invocations, reuse the exact task seed and matched context
for all six trials. The durable schedule key includes task, model, current
projection, history selection, generation posture, inference budget, and prior
self-model/epistemic projections; a changed binding starts a separate block.
`DevelopmentalExperimentStore.persist_objective_cohort_summary` accepts six
recovered v11 balanced objective runs or six v13 calibrated-family runs from one schedule block, with one trial
at each index and matching model, authority, template, history-selection,
current cognitive projection, generation posture, inference budget, prior
self-model/epistemic projection, and task bindings. It stores an immutable
digest-bound cohort summary with the six protocol, schedule-claim, and run
digests, plus
condition correctness totals, correctness by condition position, and
answer-free per-probe counts for correctness and abstention by condition and
condition position, history-associated transitions, and restoration
stability. Loading the summary revalidates every run and recomputes the
aggregate. This makes missing, duplicated, mixed, or incomplete blocks
explicit; it does not assign trial indices, randomize execution, remove order
effects, or establish learning, transfer, or model-independent development.
New v3 cohort summaries also aggregate per-probe answerability by condition
and order position, plus paired history and restoration answerability
transitions. Selective suites remain cohort-scoreable when every condition has
verified per-probe results; unanswered probes contribute unknown correctness
and a separately measured abstention. Existing immutable v2 summaries remain
loadable and are recomputed under their original correctness/abstention-only
shape. If a complete block contains older verified run summaries without
answerability transitions, persistence emits the v2 shape rather than filling
those fields with inferred values.
Calibrated v13 blocks use immutable cohort-summary v4, which preserves each
condition's aggregate Brier numerator and scored-answer denominator and reports
the weighted mean. Paired differences compare Brier error only on probes
answered in both conditions, with per-trial matched counts and numerators
retained, plus per-trial and cohort matched-answer coverage against all
trial-probe opportunities.
Each calibrated three-condition run now also stores paired Brier comparisons
for history-present versus withheld and restored versus original history-present.
The run summary binds all three condition score digests and reports the common
answered-probe count, coverage, both matched Brier sums, and first-minus-second
mean difference. Recovery recomputes this metric for new calibrated runs while
continuing to accept the prior summary shape for already persisted runs.
The paired differences are descriptive; separately reported answerability
remains necessary context. Cohort v2 and v3 continue to recompute in their
original shapes.
`ResidentEpistemicDevelopmentRuntime.process_verified_task_family_cohort`
revalidates a complete cohort before admitting its six member runs through the
existing run-level evidence adapter, including calibrated v13 cohorts. The
cohort summary itself is not added as a seventh binding, since it is derived
from those same scores; its Brier aggregates remain descriptive diagnostics
and do not independently support a family-history claim. If requested,
the runtime recomputes the task-family proposition state after the member
bindings are processed. Admission remains subject to the configured rule,
proposition scope, optional model-identity scope, and ordinary mutation
receipts. It honors the configured per-tick binding limit and accepts an
explicit remaining budget when called after other admissions in the same
maintenance tick; if the cohort cannot be fully admitted, it defers state
advancement and resumes idempotently later. If member verification or admission
fails after processing starts, the daemon records an unresolved cohort outcome,
defers that proposition for the rest of the tick, and retries from durable
member bindings on a later tick.
The maintenance daemon applies this path to eligible selected runs in the
current World-State cycle when they form a complete matched block and the
remaining evidence budget can admit its missing run bindings. Other selected
runs continue through ordinary single-run processing only for unscheduled
legacy objective protocols. A v11 scheduled run can enter task-family epistemic
state only as a member of a digest-verified complete six-run cohort; unmatched
or incomplete scheduled runs are recorded as unresolved context. This prevents
one partially observed condition order from updating the task-family history
effect proposition on its own.
This cohort gate applies to the family-level history-effect proposition.
Separately, a verified run may contribute exact evaluator-correct answers as
task-scoped historical examples when those examples are later selected into
developmental memory. Such examples remain bound to their source task and
score, with incorrect answers and abstentions kept in distinct prompt blocks;
their reuse does not admit a run to the epistemic proposition or establish a
balanced history effect.
When the variable is unset, objective interventions use the durable balanced
schedule; legacy v12 objective protocols retain their fixed order.
For v8 through v11 scheduled results, run recovery requires each condition's governed
invocation receipt and verifies that its timezone-aware receipt event time
follows the protocol's scheduled order. These receipt times are owner-reported
local event claims, not independent time authority; missing, tied, or reversed
times make the scheduled comparison unrecoverable as a valid controlled run.

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
path. Its retrieval lineage also requires a one-to-one retrieved-record ID and
SHA-256 digest vector before projecting the comparison into durable evidence.
The writeback interpretation projection preserves this text-free contrast
for later cognition to evaluate. This records which condition produced which
proposal identity and citations; it does not mark the proposal correct, executed,
or improved, and it does not establish that later cognition applied the result
successfully.

New run schema v3 summaries for companion-decision comparisons retain the
existing full-output-digest measurement and add a separate response-text-digest
assessment. The response assessment checks present-versus-withheld response
text and present-versus-restored stability independently of citation metadata,
while reporting citation compatibility and decision validation alongside it.
Any rejected condition output makes the response difference unqualified; a
history-citation binding failure is classified separately from a history
association. A history-associated response difference is qualified only when
all three outputs validate, citations match their selected history, and the
response returns after restoration. Run recovery recomputes this assessment
from the persisted decision packet and observations, and binds each available
receipt output body back to its raw output digest and response-text digest.
Rootless validated outputs require this receipt body. Historical v2 runs retain
their original summary shape. Neither digest difference nor qualification
establishes better performance or learning.

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
restoration. New decision-pattern v3 also carries the verified response-text
assessment and marks it unavailable for legacy summaries that predate that
measurement. If a condition output was rejected, digest and disposition
differences become unavailable and the relation explicitly reports rejection;
later cognition cannot mistake the rejection marker for a proposal difference.
Citation-only differences do not count as proposal differences.
The persistent history projection recognizes run schema v3 and uses the
response-text classification as its primary classification when that verified
assessment exists. It retains the full structured-output classification under
an explicit field and labels the measurement scope, so retrieval and later
reasoning can distinguish the two without losing the original digest result.
The projected history record's disposition follows the same primary
classification, avoiding a second path that could present a citation-only
structured-output difference as a decision effect. Later context assembly
recomputes the v3 primary classification and scope from the verified run
summary, then requires the source disposition and duplicated payload fields to
match those values before including the run in cognition. It also recomputes the
response-assessment posture from the verified assessment and decision rows, and
uses that posture when qualifying measurements for a different model. The
v3 posture is strictly checked. For legacy v2 records, an absent or unrecognized
posture is conservatively reconstructed from the retained response assessment
and decision rows so older history remains readable without claiming a
measurement that the record cannot support. The
primary classification and metrics remain source-attributed history. An exact
current-serving identity match marks them
applicable to the current model; a different or unavailable identity does not.
Different-model measurements remain available as explicitly source-model-only
evidence for model-transition comparisons, without establishing transfer or
model independence; missing identity remains unresolved. Ordinary history
retrieval indexes matching-model response classifications and separately
indexes identified different-model results with explicit model-replacement
terms, while leaving opaque response digests out of lexical relevance ranking.
When a run is present in the current World-State evidence, its compact prompt
projection also records the same identity relation and appends the scope
instruction; this keeps the direct-evidence path consistent with retrieved
history.
Before exposing the contrast to later cognition, retrieval rechecks that every
condition's retrieved record IDs have a matching vector of valid SHA-256 record
digests and that the decision citations remain a subset of those retrieved IDs.
The prompt keeps response digests opaque and warns that even a restoration-stable
difference does not identify the better proposal. A deterministic fake-inference
counterfactual consumes that relation in matching present/restored prompts and
changes its disposition; controls with no proposal difference or unstable
restoration do not trigger the same response. The withheld prompt has neither
the cue nor its citation. This verifies calibrated context-to-inference
behavior with a deterministic substitute, not whether a real model will
interpret the pattern correctly or make better decisions.

For a structured objective task whose descriptor explicitly requires task-family history, the resident owner projects exact, score-bound examples from the requested family with their source-model applicability posture. The record-level natural-language interpretation is omitted from that task-specific prompt, and its separate digest is not sent to the model. The enclosing record and candidate digests continue to bind the omitted source content for audit. Unrelated selected facts and embodiment/security projections are not carried into that scoped packet. Evaluator-correct examples are the only positive mapping evidence. Evaluator-incorrect examples are passed in a separate `prior_incorrect_examples` block explicitly labeled as historical errors, not mapping evidence, current truth, or authority; unknown-correctness rows remain withheld and represented by digest-only omission evidence. The task prompt tells the model not to repeat a failed answer for the same input. The durable record and ordinary history remain unchanged.

Outcome posture affects retrieval priority only when the restored score matches
the history-present score. For controlled-task-effect v2, restoration stability
also requires every probe's correctness and abstention outcome to match across
present and restored conditions; equal aggregate counts are insufficient when
per-probe outcomes differ. A favorable present-vs-withheld contrast with failed
restoration is ranked as tentative history, below restoration-stable favorable
evidence. Exact evaluator-correct examples remain available with their source
and uncertainty qualifiers when that probe is restoration-stable; unstable
probes are withheld, and the run is not treated as repeatably restoration-stable.
The owner recomputes each v2 restoration marker from its bound condition labels;
malformed or contradictory transition rows cannot produce stable guidance.
Legacy v1 and schema-less aggregate records retain their historical aggregate-only
posture because they do not contain the per-probe signature.

When eligible examples are spread across at least two distinct score-bound
runs, the prompt builder can fit a provisional integer-affine relation when
some pair of runs each supplies one evaluator-correct probe input absent from
the other member of that pair, with at least three distinct inputs in their
union, outside known unsettled task/model outcome groups in the same declared
family. It selects the pair with the largest input union, then the largest
combined unique-input count, and resolves remaining ties by sorted run digest.
It requires a one-to-one binding between
run IDs and run digests and one task, score, and source-model binding per run.
It deduplicates repeated probe inputs, rejects conflicting answers, excludes
adverse or unsettled source-outcome groups, and binds the
summary to the contributing run, score, record, and source-model digests. The
remaining runs can corroborate the deduplicated examples, but they do not
replace the selected anchor pair or count as independent trials. Adding a run
cannot remove the pair's unique probe inputs because uniqueness is measured
within the pair. The
aggregation step recomputes each bound source-model digest from its retained
identity before counting it; sources without a verified identity remain
unbound. It also requires all contributing examples to have the same target
model identity, and checks each `same` or `different` applicability label
against the bound source and target digests. The prompt-bound summary includes
each run's distinct-input count and a digest of those counts, plus the number
of bound model identities, per-identity run counts, and unbound model run count.
These summaries make the cross-run qualification and source-model coverage
auditable. The prompt instruction treats model-identity run counts and the
target identity digest as provenance, not independent trials or added evidence
weight. The relation remains historical guidance; neither learning nor
cross-model performance transfer is established.
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
and favorable. For v2 effects, restoration stability is checked at every probe,
not only by comparing aggregate correct counts. V1 and schema-less legacy
effects remain aggregate-only. Repeated references to one run
do not count twice; an unstable, neutral, or adverse comparable run prevents
this corroboration priority. This
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

New task-family trials use the v4 selective-answer contract unless they opt into
the calibrated v5 contract described above. Each probe accepts
an integer answer or `null` abstention; evaluator correctness and abstention
are recorded separately, with coverage and accuracy among answered probes
reported independently. New score records use
`sentientos.objective_task_score:v5`: when any probe is unanswered, the
aggregate status is `selective` and aggregate correctness is unknown. Per-probe
correctness and exact correct-answer counts remain scoreable, so history
comparison can measure correct answers without counting abstentions as wrong.
When all conditions retain verified per-probe outcomes, the experiment summary
and balanced cohort treat the suite as scoreable even though aggregate
correctness is unknown. Coverage and answerability remain separate outcomes;
they do not increase or reduce correctness counts.
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

The semantic-history decision qualifier now treats a missing or non-sequence
decision packet, a non-string disposition, and unknown or inconsistent output
validation status/error fields as invalid evidence instead of allowing
malformed values to qualify. Legacy packets without validation fields retain
the validated default. Explicitly rejected outputs remain an invalid-response
classif…14426 tokens truncated…t
conditions, exact selected record identities, prompt sizes, no-inference and
no-authority flags, and the counterfactual audit digest. It returned
`status=verified`: three required records at the 28,672 limit, two selected
at the 24,576 limit, with only
`devrec-5b094c92d60f2f81b21a71f5` omitted. Report origin remains unattested.
The verifier lives under `tools/`, outside the plan's pinned experiment
implementation closure; adding audit tooling therefore does not invalidate the
experiment source binding.

Run it with the plan, successful preview, and low-limit counterfactual paths
listed above. The verifier's SHA-256 is
`f67ba60c08dcf80bd8823bab6563f1e14e151d1cbcf27aa3546baf43a25ef7ee`.

### Pinned-source replay after later code changes

On 2026-11-27, rerunning the counterfactual verifier from the active checkout
rejected the saved pair because its implementation closure had advanced. The
Cycle23 plan pins 2,558 exact source files. An isolated detached overlay was
reconstructed from the retained checkout, replacing only
`sentientos/developmental_model_replacement_experiment.py`
with the plan-pinned version (SHA-256
`340a94ecc8c2fc2c69da8327fd0937628320f7f5257252d400fe3a588d373919`).
The complete implementation verifier then matched all 2,558 files and returned
digest
`2812c55f26c1ae5e4e9b23e8108b3c4ab2ff79276742266157210b1a6068995c`.
The counterfactual verifier returned `status=verified` with the saved audit
digest above. This verifies the frozen CPU preview pair against its preregistered
source closure; it does not verify the later v3 code, authenticate report
origin, or establish model learning. The plan and seeds were not rewritten.

## Schema-bound absent-evidence precondition

New cycles with no action-consequence record now persist the declared v3
history-transfer precondition schema: the result is ineligible, has reason
`no_new_action_consequence_record`, null record identity and digest, unavailable
snapshot posture, and empty evidence and provenance lists. The campaign
verifier maps that exact packet to
`precondition_not_run_no_action_consequence_record`; it does not claim a
snapshot was verified. Older compact no-schema cycle results remain recognized
for historical replay. This makes absence machine-readable without treating it
as either malformed evidence or a legacy versioned precondition.

## Current-source wide-range follow-up plan (not run)

The low-range source campaign was re-audited with the active verifier using
its original plan and two immutable cycle roots. The
[current-verifier audit](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v17-registered-model/campaign-audit-current-verifier.json)
digest is `161923855cd9f587997b2c98ae66195f3e92414d4cd0e0981cfb27e8918e0863`;
its v1 eligibility packet reports two verified score-bound source runs and
three distinct correct inputs against thresholds of two runs and three inputs.
Learning, model attention, independent preregistration timing, and authority
remain unestablished.

A first current-source replacement (plan digest
`3c12b094b04f893aa68b5b9380e23968af2fb625b0f9c9c4f8b66e1f6fe1a25a`) is
preserved but superseded before launch. Inspection of the earlier cycle-21
[failure artifact](../../../sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-20261127000100000021/cycle-failure.json)
showed 40 inference receipts from preceding stages before the later objective
acquisition retrieval gate failed. Thus its backend seed had already been used
for inference elsewhere in that cycle. We discarded that replacement's seed
assignment rather than risk reusing an exposed backend seed; no cycle from the
superseded plan was launched.

The current replacement is campaign
`rootless-history-campaign-20261127000100000027`, plan schema v9, with the
frozen cross-range history-enabled competence protocol v2. It uses fresh cycle
IDs 27 and 28 and fresh task and backend seeds not present in the retained
campaign plans. Its [plan](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-heldout-transfer-v6-current-source/campaign-plan.json)
binds the exact low-range history boundary
`0e4733ac7bba9ecfe534505ec3b5dfad12e21a8cefebc4027b6a10ff4bcbc8cb` and
has digest
`e515d86db444ed271712fde6c305f4815b0029a3c943ba5726907dd00894550c`.
Offline verification matched all 2,558 implementation pins and both model
identity recipes (implementation digest
`e6e190ccc1d0a7a5c8933d854df967ff26714e9f61fc419bce3cab9d4b1686ef`).
The identity recipe was derived from the existing manifest; no model was
loaded. Independent preregistration timing remains false.
A repository-hosted [pre-run digest receipt](evidence/cognition_goal_20261127_v6_pre_run_digest_receipt.md) binds the plan, private history bundle, and CPU preflight artifacts by SHA-256 without publishing the private bundle. It provides hosted custody only; independent preregistration timing remains unestablished.
A private [cycle launch card](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-heldout-transfer-v6-current-source/cycle-launch-card-v1.json)
(mode 0600, SHA-256 `ef1518489daec979e3ea82d70479f1a679ccf90b40c49ba84534372efad0d6f9`) binds per-cycle IDs, seeds, prior-history roots, model identity, and
launch environment. Both GPU confirmation values are unset. Cycle 28 remains
blocked until cycle 27 completes and its history chain and new CPU preflight
verify.

The plan-bound [private history bundle](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-heldout-transfer-v6-current-source/initial-history-bundle.json)
contains 12 files and has bundle digest
`e77cdecbe7626cf164ab48404fd47d64feed79b243e7d67c720517fe28a607af`.
The archive command created it from the exact v17 final boundary; no source
history files were modified.

A CPU-only owner/binder preflight for cycle 27 selected the same three
low-range source records at both stages. The new transfer probes are
`[119, 279, 469]`; the prompt is 26,428 characters under the 28,672-character
limit. The answer-free [preflight report](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-heldout-transfer-v6-current-source/cycle27-owner-preflight.json)
digest is `sha256:62a6477bdca90cb6a2ee993f942ad7662d753493b2a1f1741b46f95f9fdcbbca`.
The separate [reconstruction verifier](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-heldout-transfer-v6-current-source/cycle27-owner-preflight-verification.json)
returned `status=verified`, matched current source and model identity pins,
and records no inference; its file SHA-256 is
`e7e83e35aa1e9989dbb4a8891ad8bacfc79eb8f2a4a70dff62028ddbd3ccef57`.
It cannot reconstruct the exact future cycle prompt until the new acquisition
output and observation timestamp exist. The plan remains unrun. A CPU-only attempt to prepare cycle 28 against the
cycle-20 baseline stopped with
`planned_preflight_prior_cycle_identity_mismatch`, as cycle 28 requires cycle
27's verified append-only prefix. It created no cycle output; rerun that preflight only after cycle 27 completes and passes chain
verification. The cycle runner requires
`SENTIENTOS_HERMES_GPU_AVAILABLE_FOR_CYCLE` to equal the specific cycle ID,
and rechecks effective utilization before every inference.
Its pre-inference limit is 25%; at 2026-11-27 23:40 Indianapolis, host-wide
utilization was 37% (1,213 of 12,288 MiB in use), so the runner would fail
closed. No per-cycle confirmation was used. Telemetry does
not attribute GPU use to a particular application. This preparation establishes
neither model attention, learning, causal attribution, nor authority.
A cycle-28 replay attempted after a temporary edit to
`work/replay_planned_cycle_owner_preflight.py` stopped with
`history_campaign_experiment_implementation_mismatch` before checking the
cycle-order precondition. After reverting that edit, offline `verify-plan`
returned `operation=verified`: all 2,558 implementation pins matched with
digest
`e6e190ccc1d0a7a5c8933d854df967ff26714e9f61fc419bce3cab9d4b1686ef`.
The v6 plan is therefore bound to this exact implementation; a replacement
after any source change must use a new campaign plan, cycle IDs, and seeds.

### Reading the v6 condition comparisons

The frozen outcome verifier in
work/verify_cross_range_history_enabled_competence_outcome.py reports each
transfer probe's correctness for
history-present, history-withheld, and history-restored conditions. Its
history-associated correctness gain and cost labels describe within-task
condition differences; restoration-versus-present reports whether restoring
history matches the present condition. The verifier also reports answerability
separately, so a correctness difference must be read alongside abstention
changes.

Although the score row gives invalid-answer a correct count of zero, this
outcome verifier treats invalid-answer, truncated, and unavailable conditions
as unscoreable for per-probe transitions. They are not negative correctness
observations. Its verified-internal-consistency status confirms bindings
among the plan, scores, probes, and receipts; it is not a learning threshold.
The frozen protocol limits the claim to a history-conditioned capability
pattern; the verifier keeps learning, causal attribution, and authority
false. Even a consistent
present/restored advantage therefore requires further repeated, held-out
evidence before any durable-learning claim.

## Owner-feedback recall: historical result and follow-up

The completed response-digest campaign's cycle 1 did not meet its exact
history-conditioned recall criterion: the model abstained without citation
when the feedback record was selected, then answered without citation when
history was withheld. The historical-source audit verified append-only history,
seed-boundary, and runtime-admission chains, while cognition-recovery and
initial seed-bundle custody remained unverified. The
[CPU-only audit note](evidence/owner_feedback_recall_campaign_response_digest_audit.md)
binds the campaign and cycle result digests and records these limits. It makes
no durable-learning or causal claim.

The later neutral-query v2 run card is stale against current source pins and
must not be launched. Any successor requires a freshly pinned current-source
plan, new cycle IDs and seeds, and verified initial history/recovery custody.

## Neutral-query owner-feedback recall v2, current-source replan

The stale v2 card has been superseded with a fresh current-source plan after
correcting a preflight identity bug: the helper now uses plan-bound GPU-layer
configuration and verifies newer plan schemas. The cycle-0 CPU owner/binder
preflight and independent verifier pass; cycle 1 remains blocked until the
first cycle's history and governance chains verify. The
[evidence note](evidence/owner_feedback_recall_neutral_v2_replan.md) records
private artifact digests and the limited claim scope. The plan remains
unlaunched, independent preregistration timing remains unestablished, and no
learning or performance claim is made.
## 2026-11-28 revalidation: wide-range plan is stale

A fresh offline verify-plan against current source rejected the prepared wide-range campaign rootless-history-campaign-20261127000100000027 (plan digest e515d86db444ed271712fde6c305f4815b0029a3c943ba5726907dd00894550c). Of 2,558 implementation pins, exactly one differs: work/replay_planned_cycle_owner_preflight.py. The plan and launch card bind SHA-256 9cc235043e6b52125edcecb0431b1616dff1ee378cbe1ea0fcb1a38bb2a288b4, matching that file at card-creation commit 3490ec1cbdd412aa039ef41943c753455cd0605d; the current file is 846eba26e908ad641b138ce86b1884cc0205a26f5f461d487a5447ef9d7b23aa. This is the later owner-preflight correction to source-bound GPU-layer verification.

The card remains prepared_not_started and both planned cycle roots are absent. No inference was performed. Preserve this plan as historical preparation and do not launch it against current source. A successor needs a current-source plan with new cycle identities and seeds, plus rebuilt bundle, preflight, and card. The private answer-free revalidation report is [here](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-heldout-transfer-v6-current-source/campaign-plan-current-source-revalidation.json), mode 0600, SHA-256 1c575e157c9435fd596f3eccd170205620286e7bb6b1f1cb5c6367bc54073854. The separate neutral-query v2 current-source campaign remains the actively verified prepared plan.


## 2026-11-28 current-source wide-range replan

The stale wide-range campaign now has an offline replacement plan at
`wide-range-heldout-transfer-v6-current-source-replan-20261128/campaign-plan.json`
under the private experiment custody root. It retains the v7 wide-range task
family and cross-range history-enabled competence comparison, uses two fresh
cycle identities and seeds with disjoint generated probes, and reuses the
cycle-20 history boundary. Current-source verification confirms all 2,558
implementation pins and both model identities. The seed bundle, cycle-0 CPU
owner/binder preflight, and specialized held-out-input audit all verify. The
source audit reopened six records and found nine low-range-v6 examples, zero
wide-range-v7 examples, and no planned-probe overlaps.

A follow-up audit of the source campaign exposed a provenance gap. The
cycle-19-to-20 history and runtime-admission chains verify, but the cognition
recovery-state chain does not: the completed cycle-19 tick
`rootless-cognition-cycle-20261127000100000019:later-companion-decision`
gained `record_id` and `receipt_id` fields in cycle 20, changing a completed
tick binding. The current history projection has three score-bound correct
source runs and six distinct correct inputs, meeting the preregistered
source-count criteria. Cycle 19 alone has one score-bound correct source run
and one distinct correct input, below the minimum of two runs and three
inputs, so it cannot replace cycle 20 without weakening the protocol.

To prevent a false launch-ready result, the launch-card verifier now recomputes
the upstream source campaign chain for cross-range plans and requires its
recovery-state, seed, runtime-admission, append-only, and boundary checks to
pass. The superseding private launch card binds the source plan, roots, and
audit. Its verifier reports the source recovery chain false and both cycles
ineligible even before considering the GPU gate. The source chain must be
repaired through new score-bound low-range acquisition with append-only
recovery state before this wide-range campaign can proceed.

GPU telemetry was 39% at verification, above the 25% pre-inference limit;
no operator confirmation was set. No inference was run and no learning or
authority claim is made. The private answer-free provenance report is
`wide-range-heldout-transfer-v6-current-source-replan-20261128/campaign-source-provenance-block-20261128.json`
(mode 0600, SHA-256 `5ceb39dc6152be5ee4dd2a72624adffc81a48499d6522631bb21d880b648ec7a`).

## 2026-11-28 empty-boundary low-range source replacement

The v17 low-range campaign's two completed cycles meet its source-count
threshold packet, but the current full audit does not verify the
cognition-recovery-state chain. Its cycle-19 prefix does verify, yet provides
only one score-bound correct source run and one distinct correct input; it
cannot independently meet the preregistered minimums. The count packet does
not override the failed recovery chain.

A separate replacement was prepared from a genuinely empty initial history,
with no inherited cycle-19 records and fresh task/backend seeds. Campaign
`rootless-history-campaign-51ac975e38dde5c9b173` uses plan digest
`57bb69a650bc278ef9a907310f0cad723e7c7b19c54aec38605cda16887ccc07`.
Its two planned cycle IDs are
`rootless-cognition-cycle-1fb0d83097d130e01c45` and
`rootless-cognition-cycle-dd06328069ab1b154bd5`. The initial boundary has
zero files. Offline plan verification matched both model identities and all
2,558 implementation pins (digest
`3d316a1deadc8afc6d76ebc98270013865e5a1c43b2dca7e5fe362e823f9d8a3`).
The empty initial-history bundle digest is
`d6e9af61e03b6bd2105e0d12bf9d15e0d26ccad984173e5547cc7ceadfce3a4f`.

Before any cycle launch, the exact `campaign-plan.json` bytes were submitted to
four OpenTimestamps calendars using client v0.8.0. The local proof is
[campaign-plan.json.ots](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v21-empty-boundary-20261128/campaign-plan.json.ots)
(mode 0600, SHA-256
`3ae83e0966f3c045b54fc5ba95f34cb9200f8402cd16cfdf6335e4d9cc2cd7d0`); it
binds the plan file SHA-256
`5ba34f5e787fc9d6b3e74d32fc226cb8cc448812d22dd5a5e7e12b55834aed67`.
Immediate verification reports pending Bitcoin confirmation for all four
calendar attestations. The private
[timestamp receipt](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v21-empty-boundary-20261128/preregistration-timestamp-receipt.json)
(mode 0600) records those responses. Until a proof is upgraded and verified
against a Bitcoin block, independent preregistration timing remains
unestablished and the frozen plan's timing flag remains false. The proof was
submitted before the first model invocation. See the [OpenTimestamps client
documentation](https://github.com/opentimestamps/opentimestamps-client) for its
timestamp and confirmation workflow.

Preparing the cycle-0 owner/binder preflight exposed that the preflight helper
required a persisted composition checkpoint even though the cognition owner
treats a missing checkpoint as its canonical empty state. It also assumed a
prior-cycle identifier when independently reconstructing a cycle-0 report
from empty history. The preflight now mirrors the runtime's empty-state
default without writing it, reports no prior cycle for a zero-file boundary,
and lets the verifier reconstruct that case in a temporary empty store.
The cycle-0 preflight passed independent reconstruction with status
`verified`, plan digest above, and report digest
`sha256:1c987e6e80593704c1c5f579b8109f7e6db642205682114a419830570476d42a`.
It selected no historical records; planned acquisition inputs are `[3, 4, 5]`
and held-out transfer inputs are `[6, 7, 8]`.

A separate CPU-only seed-design audit recomputed both planned task pairs from
the frozen seeds. Together they cover four distinct acquisition input
opportunities against the three-correct-input minimum; each cycle contributes
one input not present in the other cycle, and within-cycle acquisition and
held-out transfer probes are disjoint. Its audit digest is
`1190326ecc685d770c586f8e64c11e8fcb939242f90d69ad3ab2d83901d78e59`, and the
independent reconstruction report returned `status=verified`. The seed audit
contains only planned input opportunities, not correctness observations. Cycle
0 later stopped incomplete and was not admitted to source eligibility. Both
private artifacts are in the campaign directory as
`source-seed-design-audit.json` and
`source-seed-design-audit-verification.json` (mode 0600).

The audit now has a tracked CPU-only replay verifier at
[`tools/verify_rootless_source_seed_design_audit.py`](../../tools/verify_rootless_source_seed_design_audit.py).
It loads and validates the frozen campaign plan, regenerates each acquisition
and held-out task pair from its plan seed, reconstructs the coverage and
overlap fields, checks the complete audit payload and digest, and verifies
every source implementation pin in the plan. Its report includes the matched
source count and digest. The verifier does not load a model or perform
inference. Replay returned `status=verified` with the same audit digest and all
2,558 source pins matched; the private v3 report is
`source-seed-design-audit-verification-v3.json` (mode 0600, SHA-256
`e2d9268e3dca25d54f23a2cda60af984fd47e22d6519a2cda3ef16292344e40d`).
Reproduce from the repository root with:

```sh
python3 tools/verify_rootless_source_seed_design_audit.py \
  --plan /path/to/low-range-source-acquisition-v21-empty-boundary-20261128/campaign-plan.json \
  --audit /path/to/low-range-source-acquisition-v21-empty-boundary-20261128/source-seed-design-audit.json
```

This verifies the planned input coverage only. Correctness, source eligibility,
and learning remain unobserved.

A private [launch card](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v21-empty-boundary-20261128/cycle-launch-card-v1.json)
(mode 0600, SHA-256
`ae684f95d9e99a4f5e96511aceeeb308e6f03d6a4650da6ba3c2a5c8d491a889`) now
binds the exact plan, empty history bundle, and cycle-0 preflight. Its saved
[verification report](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v21-empty-boundary-20261128/cycle-launch-card-verification-v1.json)
(mode 0600, SHA-256
`631f70220fab536a59a888beb7a0377545a91d7ea9801db365a3c13a20c02ebb`)
verified the cycle-0 preflight and left cycle 1 blocked pending its predecessor.
At 2026-11-28 07:31 UTC, telemetry showed 40% GPU utilization (3,309/12,288
MiB); the 25% limit failed, operator confirmation remained unset, and both
cycles were launch-ineligible. The verifier did not load a model or perform
inference. GPU telemetry does not identify which process owns that utilization.

At 2026-11-28 08:01 UTC, launch verification v4 reported cycle 0 eligible
(0% utilization, exact model identity and implementation pins verified, and
the cycle-0 preflight verified); it did not load a model. The private report
([cycle-launch-card-verification-v4.json](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v21-empty-boundary-20261128/cycle-launch-card-verification-v4.json),
mode 0600) has SHA-256
`2c32b16dd50695f7f3a520d248ed635d28e74b4b282b3e91dd4400206e4b7aa4`. An
initial runner attempt stopped before model invocation because its Python
environment lacked `psutil`. After `psutil 5.9.8` and `pydantic 2.13.4` were
installed in the local experiment venv, the authorized cycle-0 run proceeded
through the controlled history-intervention stage and created 21 governed
invocation receipts. It then stopped incomplete with
`ResidentDevelopmentalCognitionError: recovered_tick_intent_missing`. The
unmatched recovered record was an owner-feedback child writeback correlated to
a verified observation of the completed `later-companion-decision` tick. The
recovery sorter handled ordinary tick records but rejected this separately
identified feedback child before reaching its existing feedback-specific
recovery logic. The private [failure artifact](../../../sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-1fb0d83097d130e01c45/cycle-failure.json)
(mode 0600) has SHA-256
`e0d9448f25d8e52caf053e12c61f1b6ae7eaca596514fb1cc97e5c945462f928`. The
incomplete cycle root and receipt set are retained for diagnosis; the campaign
does not admit this cycle to source eligibility or a learning claim.

A candidate recovery fix orders owner-feedback child records after their
verified parent observation tick. This changes the pinned implementation, so
the v21 plan must not be resumed under the changed source. It remains an
incomplete, zero-eligibility experiment. A fresh empty-boundary plan with new
seeds is required to evaluate the fix. Cycle 1 remains blocked on a completed,
verified cycle 0 and recovery prefix. No independent preregistration timing,
learning, causal, or authority claim is established.


## v22 recovery-fix follow-up prepared

Plan v22, `848107d1b73aca976ace2ffadb2f8c2a914393c109b4a331f5168bc80dff8abe`,
was frozen with fresh seeds and cycle IDs after the feedback-child recovery
ordering fix was committed as `77788011730b822d75a2857146f6a6dfbb6f6631`.
Its empty history boundary has zero files. Model-free verification matched
2,558 implementation pins and both planned model identities. The initial
history bundle, cycle-0 owner preflight, and independent preflight
reconstruction all match the plan; the preflight selected no history records.

The CPU-only source-seed audit recomputed the two task pairs and found four
distinct planned acquisition inputs (`[2, 3, 4, 5]`) against the minimum of
three. The acquisition/transfer sets are disjoint within each cycle. This is
planned coverage only: no correctness or learning was observed. The audit
digest is `6bc0fee1e212bf06e9ad744c13f16e8e62f8da4a16b7b7a0d20e04b071b42651`,
and its independent reconstruction returned `status=verified`.

The exact v22 plan bytes were submitted to four OpenTimestamps calendars before
inference. The private
[campaign-plan.json.ots](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v22-feedback-ordering-20261128/campaign-plan.json.ots)
(mode 0600, SHA-256
`87a6b753c45feec690727eab7c826b1d7eb3ad420ca1318c376afa6e8b7e84a8a`), binding
plan file SHA-256
`6b0a2f0745c73432e979e8feae03ab681333efc499ea4d5e44397bb64ec89007`.
Calendar submissions have been accepted, but Bitcoin confirmation has not yet
been verified, so independently established preregistration timing remains
false.

The private [launch card](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v22-feedback-ordering-20261128/cycle-launch-card-v1.json)
(mode 0600, SHA-256
`6dfe66d8dbfbe30aebe06e284ba381df1c49c42e69ee8088c634da2b56e5484f`) binds
the plan, empty history bundle, source commit, and verified cycle-0 preflight.
The launch-card verifier returned `status=verified`, with current source pins,
model identity, bundle, and preflight all matching. It recorded 0% GPU
utilization at verification, but operator confirmation was unset, so cycle 0
was not launch-eligible. No model was loaded and no inference occurred. Cycle 1
remains blocked until cycle 0 completes and its history chain and sequential
preflight verify. The experiment is paused at this boundary while the GPU is
in use.

### v22 cycle-0 result and sequential cycle-1 preflight (2026-11-28)

Cycle 0, `rootless-cognition-cycle-e799f95c996351d4090f`, completed from the
frozen v22 plan after a cycle-specific operator GPU confirmation. It recorded
21 governed inference receipts, verified source provenance at repository
revision `af138e0d824782c496596d2f7fda5155f4081e02`, and released Hermes
(`target_model_not_resident`). Its private
[cycle result](../../../sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-e799f95c996351d4090f/cycle-result.json)
(mode 0600, SHA-256
`54715a6fd51c39c76fce952b14780efdbc223eba13c685a5dcd1fe80850e3ce4`)
records no authority, real action, or performance-improvement claim.

The low-range acquisition scored 3/3 correct. On this single task seed, the
transfer condition correct counts were `[2, 0, 2]` for history-present,
history-withheld, and history-restored; the restored answer vector matched
the present vector. This is one task-bound result, not a replication or a
durable-learning result. The separate history-intervention's withheld
companion response was rejected for citing an unselected history ID, so its
decision contrast is invalid despite present/restored output-digest agreement.
The later new-action transfer check was skipped because no new action-consequence
record met its evidence precondition.

The private [cycle-0 prefix-chain audit](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v22-feedback-ordering-20261128/cycle0-prefix-chain-audit-v1.json)
(mode 0600, SHA-256
`8cea22809cd9467c367ad14c2faae383199306e4b0112d423baa885880ddc708`)
verified append-only history, the seed boundary, runtime admissions, cognition
recovery state, and the completed cycle-0 plan binding. It covers one of two
planned cycles; the campaign remains incomplete.

The CPU-only cycle-1 owner preflight and its independent verification are
[here](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v22-feedback-ordering-20261128/cycle1-owner-preflight.json)
(report SHA-256
`f3d7544ba3a02a5d4b57854fb676f8ce1ae7289e97ce2bf44a28598465c0f06e`) and
[here](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v22-feedback-ordering-20261128/cycle1-owner-preflight-verification.json)
(SHA-256
`8eea6e820f367f42cb9980924dff32503f6b4c7045a0a0bdceb69d960bcafa6f`).
The preflight verified the append-only predecessor, current source pins, and
model identity without inference. It also reports that two of the three planned
transfer inputs overlap prior history examples (`heldout_transfer_probe_set_disjoint=false`);
any cycle-1 transfer outcome must retain that contamination limit.

Launch verification initially failed to recompute a low-range prefix because
the launch-card verifier passed the v6 seed bundle to a loader that supports
only the wide- and novel-range families. The verifier now passes that bundle
only for those supported families. The write-once v2 launch card and refreshed
verification are
[here](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v22-feedback-ordering-20261128/cycle-launch-card-v2.json)
(mode 0600, SHA-256
`3255330af98db3c894aac1dbbdc0a1429bb297bb76379e1d7051c94ca63f2acf`) and
[here](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v22-feedback-ordering-20261128/cycle-launch-card-verification-v4.json)
(mode 0600, SHA-256
`398b41c95eadd5911aeeee19b4697ee325d71cc3071dcaef33b7a6376f2ca028`).
At verification, cycle 1 alone was launch-eligible; no cycle-1 inference had
yet occurred. The v22 OpenTimestamps submissions still lacked independently
verified Bitcoin confirmation, so preregistration timing remained
unattested.


### v22 cycle-1 result and complete two-cycle chain (2026-11-28)

Cycle 1, `rootless-cognition-cycle-7252a5a251c37a0a7c40`, completed from the
same frozen plan and source revision `cc50cb1c4c38cb69b5d7acd2f9107017e72f9774`.
Its private [cycle result](../../../sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-7252a5a251c37a0a7c40/cycle-result.json)
(mode 0600, SHA-256
`e83a3ccffb0a2e042afcb296b58ef534811df3ff33e294c5538eba7c3176670a`)
records 3/3 correct acquisition probes and 39 admitted, completed inference receipts.
The model identity matched the preregistered Hermes artifact. Governed release
completed and the final residency check reported `target_model_not_resident`;
the host GPU returned to 607 MiB used and 0% utilization.

The exact-scored transfer episode recorded correct counts `[3, 0, 3]` for
history-present, history-withheld, and history-restored, with the restored
answer vector matching the present vector. However, the cycle-1 CPU preflight
found that two of three planned transfer inputs overlap earlier history
examples. Therefore this is contamination-limited within-campaign evidence,
not a clean held-out transfer result. The present/withheld/restored association
is a single-model synthetic observation, not a causal or durable-learning
claim. The separate controlled-history assessment rejected an invalid
condition response; no qualified history-associated decision difference was
established. A later new-action proposal was skipped because no new
action-consequence record met its evidence precondition. Cross-cycle owner
feedback recall was also not run because its prior-feedback reference was
unavailable. No action was executed and no authority was granted.

The private [two-cycle chain audit](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/low-range-source-acquisition-v22-feedback-ordering-20261128/cycle0-1-prefix-chain-audit-v1.json)
(mode 0600, SHA-256
`0050177eabd4de772a6efd1ce6ef44475e4541863a5fe646670959af8d95f435`)
verifies both planned cycles, append-only history, seed boundary, runtime
admissions, and cognition-recovery chain. Its aggregate low-range source
eligibility gate is met: two score-bound correct source runs contributed four
distinct correct inputs against the minimum of two runs and three inputs.
This establishes source eligibility for the protocol, not learning or
improvement. The action-history transfer precondition snapshot chain remains
unverified because no qualifying new action-consequence evidence exists.

The v22 OpenTimestamps submission still has no independently verified Bitcoin
confirmation, so preregistration timing remains unattested. Taken together,
this campaign demonstrates governed repeated acquisition and a history-linked
score contrast under this synthetic task, while leaving generalization,
durable development, causal attribution, and model-independent continuity
unestablished.


### v23 wide-range source attempt and validator correction (2026-11-28)

After v22's complete append-only chain met the low-range source threshold, a
new two-cycle cross-range plan was prepared against its final history boundary.
Campaign `rootless-history-campaign-aa5e0f4afffcbacf8093` binds 14 source
history files from v22 cycle 1 and the source chain for both v22 cycles. The
wide-range CPU owner/binder preflight independently verified before inference;
its selected records included both low-range and wide-range task-family
history, while the registered strategy source remains the score-bound
low-range evidence. All 2,558 source implementation pins and both target model
identities matched. The plan digest is
`32881f32b51ab6f14458ef9ec3fa52f02aabbe6a7b3fb6dd5470b47f9dcd03c0`.
Its OpenTimestamps proof was accepted by four calendars, but verification still
reports pending Bitcoin confirmation, so preregistration timing is not
independently attested.

Cycle 0, `rootless-cognition-cycle-5a776eaf2a0e75d8d931`, reached
`objective_cross_range_history_enabled_competence_writeback` and then stopped
incomplete with `objective_family_transfer_accumulated_strategy_invalid`.
The exact, private [failure artifact](../../../sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-5a776eaf2a0e75d8d931/cycle-failure.json)
(mode 0600, SHA-256
`709783686ada7bc42fd9f61528aa034c9aaa224d0513a222a0e98a3801630184`)
shows that the current history projector emitted
`accumulated_integer_affine_strategy:v11` inside a compact
`task_family_history_prompt_projection:v33`; the runner's receipt validator
accepted only strategy v9 for compact projections. The rejected history-present
and restored packets therefore never became a completed scored cycle. This is
a schema-compatibility defect in the experiment path, not a transfer result.

The runner performed governed unload and its final residency check reported
`target_model_not_resident`; host GPU use returned to 607 MiB and 0–1%. The
private [failure-chain audit](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-cross-range-v23-v22-source-20261128/cycle0-failure-chain-audit-v1.json)
(mode 0600, SHA-256
`58ee8e3b1a56cbe0e60427323962ada3e1ed1ebeb38a5e6949fa50f224862dc1`)
verifies append-only history, runtime admissions, and cognition recovery for
the partial cycle, while correctly reporting zero completed cycles and an
incomplete campaign. No learning, causal, authority, or transfer claim is
made. Cycle 1 was not launched.

The runner's validator now accepts the current v11 strategy schema alongside
historical v9 for compact projections and records the actual schema version in
its evidence posture. The old v23 plan binds the pre-fix implementation and is
retained as a failed attempt; it must not be resumed. A fresh successor plan
needs new cycle identities and seeds, the fixed source pins, and the same
verified v22 source chain before cycle 0 can run.


### v24 wide-range cross-range cycles and outcome (2026-11-28)

The v23 schema correction was exercised under a fresh plan rather than by
resuming the failed plan. Campaign `rootless-history-campaign-f9df3999f5254a0a0c1a`
uses the fixed runner at revision `82b404732d5133acd35720b4f7f7f536e28d164d`,
new cycle IDs and seeds, and the verified final v22 history boundary
`07ceeb14ff2533791f33f9230d8d3f4a75a7ebbada82f98e64102fec68729fe3`.
The plan digest is
`1209ee625e8bdcff1b6e97400139018c61c64ce1c4d6191e5bf83982d762613d`.
Both planned cycles completed, including the cross-range projection/writeback
stage that rejected v23. The private [two-cycle chain audit](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-cross-range-v24-strategy-v11-20261128/cycle0-1-prefix-chain-audit-v1.json)
(mode 0600, SHA-256
`4bc1bfd422ec6ca0ef5936660f4826894decc2ae3227a540be016b0d173c588d`, audit
digest `a4586853321d76b0f3bc0461dceda42efd83676d41ece7a7d354ff42f0039b76`)
verifies both cycles, append-only history, seed boundaries, runtime admissions,
and the cognition-recovery state chain. The action-history precondition chain
is false; no action-authority claim is supported. The plan’s OpenTimestamps
submission still lacks independently verified Bitcoin confirmation, so
preregistration timing remains unattested.

The two private cycle results are
`rootless-cognition-cycle-28df232144e93508a41a` and
`rootless-cognition-cycle-0257555a60152d84fbdf`. The first wide-range
acquisition scored incorrect; the second scored correct. In both cycles,
the cross-range history-enabled competence intervention completed, but the
separate developmental outcome assessment rejected the history-withheld
condition as invalid. Consequently, the transfer stage was skipped because
withheld-history baseline competence was not demonstrated. Neither cycle
established a history-associated decision difference or performance
improvement. Cross-cycle owner-feedback recall was not run because the prior
feedback reference was unavailable. No action was executed and no authority
was granted.

This result resolves the v23 validator incompatibility and demonstrates that
the registered pipeline can complete its cross-range writeback. It does not
show that low-range accumulated strategy transfers to the wide-range task:
the acquisition scores were mixed, the intervention’s required condition
comparison was invalid, and transfer was gated. The next experiment should
repair or preflight the condition-response validity check and ensure the
owner-feedback reference is bound before inference. It should retain
independent scoring and held-out probes, then require a valid withheld
baseline and present/withheld/restored comparison before interpreting
transfer. No learning, causal, durable-development, or model-independent
continuity claim follows from v24. Governed unload completed after both
cycles; each final residency check reported the target model not resident,
and host GPU use returned to 607 MiB and 0% utilization.


For the rejected withheld-history semantic decision, the private cycle result
records `companion_interaction_history_id_not_allowed`: the model returned
an answer carrying a history citation that the withheld arm was not permitted
to use. The response digest also matched both the present and restored arms.
The validator correctly rejected this as a condition-invalid output, rather
than counting the nominal abstention disposition as a valid withheld response.
This localizes the immediate protocol failure to the model reusing
history-conditioned content in the withheld condition; the audit does not
establish whether the cause was model behavior or an inference-context issue.
The qualification output now binds each arm’s response digest and identifies
when a rejected withheld response exactly matches both the valid present and
restored responses. It continues to reject the condition and grants it no
learning weight; the added classification makes this failure mode explicit
for later audits without attributing its cause. Before the next full campaign,
run a no-inference prompt-binding diagnostic for the three arms and then a
small scored diagnostic. Bind the owner-feedback reference before inference.


### CPU-only companion history prompt preflight (2026-11-28)

The resident cognition owner now exposes
`preview_companion_history_intervention_conditions`. It runs the same
request-building and history-binding path as the controlled companion
intervention, but stops before invoking the model. It checks that present and
restored requests bind the same protocol records, the withheld request binds
no records, the withheld selection is explicitly marked withheld, and no
protocol record ID or digest appears in the withheld prompt. It also requires
identical present/restored prompt digests and a distinct withheld prompt.

The returned summary includes request and prompt digests, record bindings,
and explicit `inference_performed: false`, `learning_established: false`, and
`authority: false` fields; it omits prompt text. The preview tick is removed
from incomplete state before returning. This gives the next campaign a
model-free check of the real withheld-arm prompt construction before any
scored inference. The owner API has been syntax-checked; a campaign preflight
has not yet been run with it.
