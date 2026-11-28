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
classification. Valid packets still
require the ordered present/withheld/restored decisions, exact recalled token,
bound history citation, matched controls, and restoration-stability evidence.
The direct history-transfer qualifier likewise rejects non-sequence condition
packets and non-mapping condition rows before it reads prompt digests or
controls, and requires every output to have validated status with no validation
error before a transfer difference can qualify. It also recomputes the
response-text digest for each condition before accepting its output binding.
Qualification schema v5 reports that digest-binding result consistently for
evaluated and precondition-skipped transfers, and records the all-condition
decision-validation result directly.
The rootless cycle's
historical-recall summary now carries the
resident observation's digest vector into each reported condition and accepts
citations only as unique, non-empty string record-ID sequences. Retrieved IDs
must align one-for-one with valid SHA-256 record digests, cited IDs must be
among those retrieved records, and the condition exposes its cognition
observation identity. Before qualification, the runner joins every live
condition capture to the reloaded, verified experiment observation by
observation ID and checks its observation digest, receipt identity, prompt and
control bindings, and complete retrieved-ID / digest vectors. It also joins
the capture to the reloaded companion-decision packet and checks receipt and
output identities, recomputes the response digest, and compares disposition,
validation status, evidence citations, and history citations. A mismatch
aborts the cycle instead of producing a qualified history claim. It also
requires exactly one capture for each of the present, withheld, and restored
conditions, so duplicate captures cannot mask an omitted arm. The cycle result
uses schema v17 for the persisted matched-input packets and receipt, record,
and observation identities on both later intervention arms. It now reports
the exact-scored task-family acquisition as its own top-level result, including
scoreability, baseline outcome, and writeback references, even when transfer is
skipped for insufficient baseline competence. This keeps acquisition evidence
visible independently of transfer eligibility. The result also records a
source-run score-to-history binding for eligible acquisition writebacks. The
audit filters history examples by the exact acquisition run ID, then requires
one projected experience, the history-present score digest, and matching
correct, incorrect, abstained, and unknown outcome counts before transfer can
start. A mismatch fails closed; the persisted binding exposes counts and
digests without answer values and does not claim that learning occurred.
The result also records a
bounded diagnostic row for each rejected decision: condition, validation code
and domain, output-text integrity status, raw-output parse status and
disposition enum, output digest, digest
of a parseable raw response, whether that
digest matches either valid arm, citation count and condition-compatibility
posture, and an explicit `decision_qualified=false` marker. The rejected output
text and citation IDs are not retained or promoted into decision evidence.
Older cycle artifacts retain their original schema. These checks harden artifact
interpretation; they do not change the experiment's learning or performance
claims.

Run recovery now re-verifies persisted invocation receipts for rootless
observations, including unscheduled companion-intervention runs. For validated
companion decisions, recovery binds the receipt's optional output text back to
its output digest and byte count, requires it to be untruncated, and then
recomputes the response digest before accepting the decision packet. The
receipt digest by itself does not cover the optional output-text field, so this
explicit binding is needed before that text can serve as recovery evidence. A
self-consistent run digest and stored response digest alone therefore cannot
stand in for the original authenticated model output after restart. This
recovery also checks that an explicitly rejected rootless response carries
the fixed `INVALID_EXPERIMENTAL_RESPONSE` marker digest. This
strengthens provenance recovery; it does not establish learning or performance
improvement.
The shared invocation-receipt validator now applies the same output-text
digest and byte-count binding to every complete optional receipt body, so other
recovery consumers cannot treat detached text as verified output either.

## Persisted synthetic acquisition observation

The persisted rootless cycle `rootless-cognition-cycle-1e3f877fb56242c5b2c0`
contains acquisition run `devexp-run-ac5c6e94e3114ab74169e4a5` under
protocol `devexp-protocol-a3dc9f257964519b3741a65b`. The exact-scored affine
task asked for outputs `[3, 4, 5]` from verified examples `(0, 2)` and
`(1, 5)`, so the oracle outputs were `[11, 14, 17]`. All three condition
receipts returned `[8, 11, 14]` with the same output digest; the scorer recorded 0/3
correct for present, withheld, and restored. Since the preregistered withheld
baseline required at least two correct probes, transfer was correctly skipped.
This is evidence of an unsuccessful synthetic baseline-competence screen and
no observed response difference in that episode. It does not establish a
history effect, durable learning, or real-world performance.

## Bounded projection capacity for larger acquisition suites

The v20 rootless campaign's second cycle stopped during acquisition projection
with `run_projection_payload_over_bound`; it produced no terminal cycle result
and supports no learning claim. Its canonical source run was 49,267 bytes,
including the 12-probe evidence and transitions. The projection had retained
answer-free transitions for all conditions and history-present examples for
future retrieval, so the prior 32 KiB per-record ceiling could reject a valid,
bounded run artifact as the probe suite grew. The projection ceiling is now
64 KiB per record. This remains a hard bound, independent of the source
artifact's own canonical size limit; it does not relax receipt validation,
score binding, or the evidence needed to establish learning. A fresh plan and
new cycle identities are required before another inference attempt, and the
failed v20 cycle is retired.

The follow-up plan v21 is frozen at
`eacc76f88c9ad38eb6741f00e8d948f4e3974db759e314edbc49558c0cb4553d` and is
stored with the campaign artifacts. Its initial history boundary is
`2576659078c4a4764ef97c3640eae2b2bf599449b5ba191c06f2cfca48905b7c`, taken
from the completed v20 cycle's retained history. It preregisters two fresh
cycle IDs, 12 acquisition probes, and 12 transfer probes per cycle under the
same two-thirds baseline-competence gate. Model-free verification matched all
2,557 implementation pins and both seed-specific model identities; no
inference occurred during plan creation or verification. This new plan is
separate from the retired v20 campaign.

The initial v21 launch was rejected before inference because the backend seed
was passed using the wrong environment variable name. The runner recorded
`history_campaign_seed_binding_mismatch` at model/runtime preflight, with no
failure result or inference receipts. That launched cycle ID is retired; v21 is
not reused. Plan v22 is frozen at
`ae52cd133dddd60fb5f461e5f45190b8aa090e52db2d5dffc9bfc495b2a53017` with new
campaign and cycle IDs, the same explicit v20 history boundary, and corrected
runtime seed binding. Its model-free verifier again matched all 2,557
implementation pins and both seed-specific model identities; inference had
not occurred at freeze time.

The v22 cycle also stopped at model/runtime preflight: the runner's per-cycle
GPU availability assertion was absent. It recorded
`gpu_owner_availability_confirmation_missing_or_mismatched`; no model inference
occurred, and that cycle ID is retired. Plan v23 is frozen at
`e72d80f6fc280d7ee1c11a16a2f42f27a2596c2c77abef3fda1d3de64e187ba7` with new
cycle IDs. Before launch, the runner's
`SENTIENTOS_HERMES_GPU_AVAILABLE_FOR_CYCLE` must equal the selected cycle ID;
this is bound to the user's explicit GPU availability authorization and is
recorded as an operator assertion, not inferred from telemetry. The v23
model-free verifier matched all 2,557 implementation pins and both model
identities.

v23 cycle 0 completed under plan digest
`e72d80f6fc280d7ee1c11a16a2f42f27a2596c2c77abef3fda1d3de64e187ba7` with 44
invocation receipts, verified source provenance at `e29b44141`, and governed
model release. The acquisition scored all 12 probes in each condition; all
three conditions had 0 correct, below the preregistered threshold of 8. The
withheld-baseline competence gate therefore skipped transfer. One structured
history response was rejected for the withheld condition, so the cycle
classifies the history decision comparison as invalid. It establishes no
learning, improvement, changed action decision, or real-world consequence.
Its answer-free 172-file evidence manifest is
`cycle-0-v23-evidence-manifest.json`, digest
`65d923f727b0acf5f35422637f6142df54621fd5e908063187a6651f83ea9728`; the
exporter re-verified it against the completed cycle root.

v23 cycle 1 completed from cycle 0's retained history with 56 invocation
receipts and governed model release. Its 12-probe acquisition again scored 0
correct in each condition, below the threshold of 8; transfer was skipped.
The withheld structured history response was rejected, and the result
establishes no history-associated decision difference, learning, or
performance improvement. Its answer-free 198-file evidence manifest is
`cycle-1-v23-evidence-manifest.json`, digest
`a44160150c65a88500422c5e95fe71979c4e711e2cef80f67ce7c444599102d4`,
re-verified against the completed cycle root. The independent campaign audit
`campaign-audit-v23.json` (digest
`98858e517da9048a89fdcef3e73aef23a2a29360814be00bc321d7f6c7727ec7`)
verified both planned cycles, the append-only history chain, seed boundary
chain, runtime-admission chain, and cognition-recovery chain. It records two
source runs and leaves `learning_established=false` and `authority=false`.

## Withheld-history citation failure and prompt revision

Both v23 cycles rejected the withheld-condition companion response with
`companion_interaction_history_id_not_allowed`. Receipt-bound diagnostics show
the model emitted one history ID even though the withheld observation retrieved
no history records: cycle 0 cited a prior record that was not delivered, while
cycle 1 emitted a placeholder ID. The owner correctly rejected both outputs;
neither response was promoted into a valid history decision. The shared prompt
already required an empty citation list but did not explicitly require an
abstention sentinel when a historical question had no eligible records.

The shared history-intervention instruction now says that, when the history
allowlist is empty and no independent fact or retained memory supports the
answer, the model must abstain with `HISTORY_UNAVAILABLE`, leave citation arrays
empty, and not reconstruct an answer from parametric recall or another
condition. This applies uniformly across the intervention conditions. The
receipt and citation validator remains fail-closed; invalid citations are not
normalized into valid decisions. A fresh plan is required to measure whether
the stronger instruction improves response qualification.

That follow-up is frozen as plan v24,
`088a335bed520ba424bacc287c7c284c1b4c1cf4b06876482cc316f8e12df30a`, using
the completed v23 cycle 1 history boundary
`2d655527a32bf6c41d3288c129071b4d2ad1aac5978383ff0ee8310904c16454`. It
preregisters two fresh cycles with 12 acquisition and 12 transfer probes each.
Model-free verification matched all 2,557 implementation pins and both model
identities, with inference false at plan freeze. The plan is bound to source
commit `9508ca268` containing the shared prompt revision.

The first v24 cycle then failed before companion delivery with
`cognition_input_budget_exceeded`: the zero-history prompt was 24,646
characters against the fixed 24,576-character limit. The failure artifact
records zero hosted companion deliveries, and governed release found Hermes
not resident. The v24 cycle ID is retired. The abstention guidance has been
shortened without raising the input limit; a new plan must bind this revised
prompt before another inference attempt.

Plan v25 replaces the retired v24 campaign. Its digest is
`720511619016e0370e09e69235453ecc975042b4e02b2aba32b8378a621ae6d7`; it
retains the v23 cycle 1 history boundary and preregisters two fresh cycles with
12 acquisition and 12 transfer probes each. The compact abstention guidance is
bound to source commit `cdb285601`. Model-free verification matched all 2,557
implementation pins and both seed-specific model identities, with inference
false at freeze.

## v25 outcome: prompt delivery did not change qualification

Both v25 cycles completed and were independently audited. The campaign audit is
`campaign-audit-v25.json` (digest
`9f15ee7e605432eb2e36063b15d42cd03e2bec3f5cf31d30ca2780c086326838`). It
verified both planned source runs, append-only history, seed-boundary,
runtime-admission, and cognition-recovery chains. It records
`learning_established=false` and `authority=false`.

Cycle 0 (`rootless-cognition-cycle-602f64167f4c03a65092`) completed all stages.
Acquisition reached the preregistered baseline competence threshold with 9/12
withheld probes correct (present 12/12, restored 12/12), so held-out transfer
ran. Transfer scored 0/12 in every condition. The history-associated answer
vector differed, but its correctness effect was zero; the withheld companion
decision remained invalid because it cited an unavailable history ID. No
learning or action consequence was established. Its answer-free evidence
manifest is `cycle-0-v25-evidence-manifest.json` (digest
`4e4d1d697fa89efaecf1ba547bf7705c281396fd726765edbf474bc1191d1b9b`).

Cycle 1 (`rootless-cognition-cycle-a63ca03a3d2f753db69d`) completed, but scored
0/12 in each acquisition condition, below the threshold, so transfer was
skipped. Its withheld companion decision was rejected with the same
`companion_interaction_history_id_not_allowed` code. Its answer-free evidence
manifest is `cycle-1-v25-evidence-manifest.json` (digest
`7759bdcbe59eb428a0314b140b712a005ed6efb11f57769b8d9c639bb7500538`).

A receipt-bound comparison against v23 shows the revised instruction was sent:
the withheld request's instruction digest changed from
`sha256:1ed69...` to `sha256:0e91...`, while its schema, budget, and question
digests stayed fixed. Yet both v25 cycles emitted the same raw response digest
as v23 (`4d6cf0...`) and the owner rejected it. This is evidence that the prompt
change was delivered but did not change this model's output in these trials;
it is not evidence that the system learned to abstain.

The campaign audit also reports
`history_transfer_precondition_snapshot_chain_verified=false`. Inspection of
the bound cycle results shows the separate companion action-consequence
qualification did not run: both persisted a compact summary with
`classification=not_run_no_action_consequence_record` and
`reason_code=no_new_action_consequence_record`, without a schema version or
record ID. The v25 verifier reported this as `unbound_legacy_precondition`,
which conflates a no-run state with an older versioned precondition. The audit
still verifies the source runs and append-only history chain, but no action
consequence record existed to snapshot-bind. A verifier improvement now
classifies this exact state as
`precondition_not_run_no_action_consequence_record` and reserves the legacy
label for versioned older schemas. This makes the reason for the false chain
status explicit; it does not turn the skipped qualification into verified
evidence or alter the immutable v25 audit.

A fresh model-free replay of the same two cycle roots with the current verifier
produced the answer-free
[campaign-audit-v25-current-verifier.json](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/campaign-audit-v25-current-verifier.json),
digest cdef6ab18eeabb5db486ad24b8b60bb0302588d1eeaf8492aa74eacd303cd76b.
Both rows now report precondition_not_run_no_action_consequence_record; the
precondition chain correctly remains false because neither cycle produced an
action-consequence record. The audit retains verified source-run, append-only
history, seed, runtime-admission, and cognition-recovery chains. It still records
no learning, authority, or independent preregistration attestation. The original
v25 audit and both immutable cycle manifests remain unchanged.

## Confidence-saturation reanalysis of v23 and v25 acquisition scores

The v6 confidence auditor reprocessed the acquisition scores for these two completed campaigns. It verifies each acquisition-run digest, selected-history record digest and posture, campaign audit chain, per-cycle source-run binding, and score-level abstention representation and agreement between each score's status/correct fields and recomputed probe outcomes. For schema-v6 scores, answered probes must omit the abstained marker; abstentions must carry abstained=true with no observed answer or confidence value. Aggregate status must be selective when any probe abstains, otherwise correct only when every probe is correct. These reports cover objective task-family acquisition conditions; they do not re-score the separate companion-history citation outcome or transfer probes. Both campaign audits report the transfer-precondition snapshot chain as false, which v6 preserves explicitly while limiting its result to acquisition scores.

In v23, 28 probes were answered and none were correct; 44 were abstentions. In v25, 38 probes were answered: 33 were correct and 5 were incorrect, with 34 abstentions. Every answered probe in both campaigns carried the maximum reported confidence of 10,000 basis points. This is confidence saturation in these saved probes, not a calibration estimate.

The v25 acquisition results came from cycle 0: history-present and history-restored scored 12/12, while history-withheld scored 9/12. Cycle 1 scored 0/12 in each condition; its report shows one incorrect answer each in present and restored and abstention on all withheld probes. These acquisition results align with the existing transfer gate record: cycle 0 met the withheld baseline threshold, while cycle 1 did not. They do not overturn the separately reported 0/12 transfer scores in cycle 0.

v23 and v25 are not a controlled before-and-after comparison. Their task-generation and backend seeds differ, and their pinned model-identity digests differ. Of the 2,557 implementation pins, resident_developmental_cognition.py is the only path whose digest differs between the plans. The observed acquisition difference therefore does not show that the prompt revision, retained history, or system development caused the score change. Neither campaign establishes durable learning or calibration.

The answer-value-free v6 reports are [v23](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/confidence-diagnostic-v23-v6.json), digest `698e1be44825c68b434ed9a9d6f7de469ee482f6d72dadc558e3e8b56c2bb798`, and [v25](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/confidence-diagnostic-v25-v6.json), digest `e46493b74a7a6a3b1226a86954d9fc296f5a9b8dfe0d1687f7238fc72e113a12`. Each confirms the campaign source-run bindings and preserves the false transfer-precondition chain status. Both report no learning, model attention, calibration, or authority. Earlier v3, v4, and v5 reports remain unchanged as historical audit outputs.

## Next cognition gap: rejected decisions do not become feedback

The cycle result binds each companion condition to its validation outcome, but
that outcome does not enter developmental history. In cycle 1, the withheld
condition again failed with
`companion_interaction_history_id_not_allowed`; its answer-free diagnostic
binds the same raw-response digest as the earlier trial and marks the cited
history incompatible and the decision unqualified. A full-tree search of
cycle 1's retained artifacts found neither that failure code nor that prior
raw-response digest in its inherited cognition history. The prior cycle's
rejection therefore was not available as an explicit retained experience in
the next cycle. The controlled intervention intentionally avoids writing
history during its present/withheld/restored conditions, so this feedback must
be appended only after all three conditions have completed.

An owner-authored performance record is now created after
`run_companion_history_intervention` has validated all three captures. The
withheld-condition citation rejection is bound to its persisted cognition
observation, invocation receipt, validation code, retrieved-history allowlist
digest, and qualification result. The complete request is checked against the
verified receipt before writeback, while retained provenance stores only the
request identity and digests of the prompt, model identity, schema, budget,
upstream evidence, and linkage. It does not retain the prompt, upstream
evidence payload, or rejected answer text. The record keeps
`decision_qualified=false`, `current_truth=false`, `authority=false`, and
`canonical_explicit_user_retention=false`. It uses a distinct
`owner_verified_companion_qualification_feedback:v1` candidate kind and the
existing separately admitted writeback path. Append and recovery validation
allow an empty selected-fact set only for this typed feedback candidate; the
model-authored lesson candidate contract remains separate. The generic bounded
history packet exposes only the short interpretation and its epistemic status,
not the rejected answer or full receipt. Recovery validates this typed feedback
record against the dedicated resident-developmental-companion-feedback
operation prefix, exact recovered tick, and candidate ID. Ordinary lesson
writebacks retain the resident-developmental-writeback prefix. Because the
feedback append occurs after the controlled intervention tick is already
checkpointed, it receives its own deterministic child tick derived from the
parent tick and candidate ID. Recovery appends that child checkpoint from the
record/receipt commit point; it never fills or revises the parent checkpoint.
Legacy feedback records that correlate to the parent are mapped to the same
child tick during recovery unless a historical checkpoint already contains the
exact feedback pair; that already-mutated row is preserved without creating a
duplicate. Repeated recovery is stable, and conflicting record or receipt
bindings remain errors. Candidate provenance binds the feedback to the parent
intervention observation. The controlled history trials retain the direct model
response so
its digest remains bound to the invocation receipt. Serving-time freshness
normalization continues to apply to ordinary companion decisions; trial
outcomes are measured without that post-inference rewrite. The general
historical cue also matches both the forms previous and previously.

A CPU-only recovery replay of disposable copies of the retained cycle-19 and
cycle-20 stores is recorded in the [recovery report](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/owner-feedback-recovery-replay-v4/recovery-report.json),
SHA-256 `cb1ec49e3e3e17d307a211cb8fc7b7f4bb23efe3ef1ee513ce4229e56ce46c2d`.
Production owner recovery preserved each parent row, bound recovered child
ticks to their exact feedback record and receipt, avoided duplicating the
already-mutated cycle-19 parent in the cycle-20 snapshot, and produced
byte-identical persisted state on the second recovery. The replay loaded no
model and performed no inference; it validates recovery mechanics only and
establishes neither learning nor authority. The original campaign audit remains
a historical record with its cognition-state chain marked false.

The rootless cycle runner now has an explicit cross-cycle recall probe. In a
later campaign cycle, it follows the immediately preceding cycle's result to
the exact feedback record and writeback receipt, verifies that pair in the
seeded history store, and runs the existing present/withheld/restored
intervention with that record as the only allowed history item. A missing or
inconsistent prior result, record, or receipt prevents the probe. The score
requires exact expected responses and dispositions, selected-record identity
and digest, history citations, empty evidence IDs, an explicitly validated
decision, matched non-history inputs, and exact prompt restoration. The result
reports selection, citation, response, decision-validation, and
condition-criterion assessments separately. A criterion match requires all
protocol checks, including explicit decision validation; a missing validation
status fails the criterion. Response
matching and validation status have separate assessments, so missing validation
evidence does not obscure whether the response itself matched. Selection
alone is not treated as model use: a selected record without its citation is
reported as selected but not cited. These observed checks still do not establish
that the model cognitively used the record or that it caused the response. The
summary stores IDs and digests rather than model output text.
Its fixed query and scoring rules are frozen in
`owner_cognition_feedback_cross_cycle_recall_protocol.json`; its digest must
be supplied before the campaign starts using
SENTIENTOS_HERMES_OWNER_FEEDBACK_PROTOCOL_DIGEST. This is a separate binding
from SENTIENTOS_HERMES_PREREGISTRATION_DIGEST, which must match the campaign
plan digest. The protocol digest is SHA-256 of the protocol JSON encoded as
UTF-8 after normalizing CRLF and CR line endings to LF, in lowercase hexadecimal
without a prefix. The run preregistration records both digests; the runner
checks the feedback protocol digest against the frozen JSON before it enables
the follow-up probe. The campaign plan separately binds the source and model
implementation hashes.

Protocol v2 is a forward-only neutral-query variant. It defines the allowed
status vocabulary QUALIFIED, UNQUALIFIED, and UNKNOWN, but not which status
applies; the expected status for each condition stays in the frozen scoring
rubric. The runner chooses v1 or v2 only when
SENTIENTOS_HERMES_OWNER_FEEDBACK_PROTOCOL_DIGEST matches that protocol file.
The v1 file and completed v1 result are unchanged. The current v2 protocol
digest is eadf7e24dea6c21b7017464b6ccc46ed672fd2d99c65db7e158c26623cea27ac.
It has not been run. A two-cycle plan is prepared at
rootless-experimental/rootless-history-campaign-ddb80885d1c7d39e634f/campaign-plan.json.
Its v11 plan digest is
9b245a3af1dc016904d819428f6a59561a33ef8f47ab93f87b3561d852a739d0. Offline
verification reports current source and model identity pins match and
inference_performed=false. The plan binds a history boundary digest of
bedca4464283f06e3180850ec144dd65ec79c92fc1a4149b4543a55b34575956 and two
fresh novel-range cycles with three acquisition and three transfer probes
each. Its preregistration_timing_independently_attested field is false. The
v2 protocol digest is a separate run-preregistration value supplied through
SENTIENTOS_HERMES_OWNER_FEEDBACK_PROTOCOL_DIGEST; it is not embedded in this
campaign plan. The v11 plan's launch binding was
campaign-run-card-v2.json. On 2026-11-27, CPU-only `verify-plan` recomputed all
2,558 implementation pins and both model identity recipes: implementation
digest `a7f04b1b1845ee559aed9953173b70453288cc2fdfc055f6e841affdbfa35ec5`,
with source and identity pins matching. A separate custody check confirmed the
private v2 run card agrees with the frozen plan on campaign ID, plan digest,
cycle order, and task/backend seeds; its protocol and manifest digests match
their pinned files, and both cycle entries remain `prepared_not_started` behind
a per-cycle GPU confirmation gate. The mode-0600 run card SHA-256 is
`79ae1b03f7afd5386a5b561af307485fd8a11044d358812a653f2dfa2f85132a`.
The read-only [run-card verifier](../../tools/verify_owner_feedback_campaign_run_card.py)
also checks the initial history boundary, cycle-to-cycle history path, all
ordered IDs and seeds, custody mode, and required per-cycle GPU gate. Its
SHA-256 at the v11 verification is `893e665cc472337d8ddf57a7ef586a14bab60d34a72be37ed912ca558a7847ff`;
that prepared card passed all 16 checks. It validates launch custody and current
pins without loading a model. The helper was added after plan freeze and is not
part of the plan's pinned experiment implementation; its digest is recorded
separately. No inference was performed by either check. The run card's launch bindings and hash are custody metadata, not independent
timestamp attestation. Even a passing single-record v2 probe would show only a
protocol-bounded neutral-query
recall result, not generalization, durable learning, or causal use of history.

### Higher-resolution neutral-query v2 plan

The v11 neutral-query plan above remains preserved and unrun. A replacement
schema-v14 candidate was prepared with 12 acquisition and 12 transfer probes
per cycle, keeping the novel-range task family and the same initial history
boundary. This increases the number of scored observations before the
baseline-competence gate and leaves the prior v11 plan unchanged.

The private plan is
`rootless-experimental/owner-feedback-recall-campaign-20261127-neutral-v2-12x12/campaign-plan.json`.
It binds campaign `rootless-history-campaign-d8f0bc296251426a8da2`, plan digest
`6575bd8cc9f4d9135c186437d7395e5733b1a2d98c8940cf0e2accdebadca972`, and
history boundary digest
`bedca4464283f06e3180850ec144dd65ec79c92fc1a4149b4543a55b34575956`. Its
cycle IDs are `rootless-cognition-cycle-f693f18b055e42fca02b` and
`rootless-cognition-cycle-0fbcd3dc1a5e406b9aae`; task-generation seeds are
1149774101 and 781169057, and backend seeds are 21902234 and 1942124107.
The model manifest and v2 protocol digest remain bound separately as recorded
above. CPU-only `verify-plan` matched all 2,558 implementation pins and both
model identities. In particular, the plan pins
sentientos/resident_developmental_cognition.py to SHA-256
e6ff318a6b3314875cecfd76faa1f5b1646e4713eb3e6fd53ae5415537c96ea5, which
includes commit ba099ceda and matches the current source file. The updated
run-card verifier SHA-256 is
`482b7680ee1665a71bbcfc8f0761ece9508f0298b09b48b536613421db24994b`. The
revised private `campaign-run-card-neutral-v2-12x12-rev2.json` binds
the task family, probe counts, and initial-history digest explicitly. It passed
all 18 checks, including the previous-card digest link, in the updated offline
run-card verifier; its mode-0600 SHA-256
is `67fb0e15870e4f4c63bc22bd9c04729c3ac389542a202253549ee29779624960`.
Both cycles remain `prepared_not_started`; no inference was performed, and
preregistration timing is not independently attested. This is only a stronger
measurement plan. Even a fully qualified neutral-query result would not show
durable learning, general transfer, or causal development.

The launch custody audit was repeated on 2026-11-27. The ordinary cognition
development checkout rejects this frozen run card because its confidence
auditor has changed since the plan freeze; a detailed failure now identifies
that single implementation pin as
work/audit_rootless_campaign_confidence.py. To preserve the experiment rather
than re-freeze it, a dedicated
source checkout was prepared at
/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/cognition-goal-20261127-v2/source-neutral-v2-frozen-audit-snapshot,
branch codex/neutral-v2-frozen-launch-20261127, commit
cbc6ab69fbfc3082f669357715ac14f4abc632de. It retains the current 2,557
other implementation pins and restores the auditor file to the exact
plan-pinned SHA-256 7f4d5a7c4499e32450a1977cd627ab894bbe34da7318085e668418194e841e9f.
The unchanged run card then passed all 18 offline custody checks, including
source pins and cycle history lineage. Its answer-free result is
[neutral-v2-12x12-run-card-verification.json](../../artifacts/experiments/ordinary-chat-retention-20261127/hermes-score-bound-acquisition-v1/neutral-v2-12x12-run-card-verification.json),
digest f0632f65c51e49c95a7a9d2c3d50e043c8b40a0864a3fcfa3bc666d85ca8bdef. A
separate Git-tree comparison confirmed the remote development snapshot and
frozen-launch branches exactly matched their local checkouts across all 11,948
tracked repository paths at the listed baseline commits. Their pre-attestation
tree SHAs are f90b82cf6bdcce324ce03307130d8824f32832fd and
30a6eb0b5dc5faea707907360e0171050747c938. The report and this note were appended
after that comparison, so their final branch trees require a fresh comparison.
The campaign plan, history boundary, protocol, and run card were not changed.
This only restores launch custody for the frozen experiment; both cycles
remain prepared_not_started, and no inference or learning result exists.

### Earlier exploratory 12-probe recovery attempts

Two earlier schema-v14 recovery campaigns used the same initial history
boundary and model manifest, but they froze different source revisions and
different plans. They are exploratory records, not matched replications and
not runs of the neutral-query plan above.

Campaign `rootless-history-campaign-8b56228e154e42c8ab14` used plan digest
`0ab7515cc8682cab751a1a7a9d112485fef6307dd84d3e4f04abf56905f6e642`, task
seeds 171234571/171234572, and backend seeds 2149/2927. Its cycle 0
(`rootless-cognition-cycle-57ad73290576484f93f2`, source revision
`dc349b9a2655b7b46e5a2a0b5ea3fb3f89b7c409`) completed with acquisition
condition counts `[12, 0, 12]`. The frozen baseline threshold was 8, so the
baseline gate was not met and transfer was skipped. Its cycle-result SHA-256
is `7ec6b8b78510432b7b3f024073d3bbddeecaedea7a7961affbb55286cbbf1cf8`.
Cycle 1 (`rootless-cognition-cycle-7824344d72b64d1393d5`) did not complete;
recovery stopped at `controlled_history_intervention` with
`run_artifact_companion_response_digest_unverified` and no cycle-result.
Its failure-record SHA-256 is
`5b900e4f6e0209bf34bedf1606f8ff9725a1d302b992c30c1cd0b4b7e6c5dd94`.

Campaign `rootless-history-campaign-b49a65aa77294c74b8ac` used plan digest
`2597540ceab8cb3b34e7dad938fed3d8c8ddf2af697f66b6db772c6392bc1cf5`, task
seeds 171234569/171234570, and backend seeds 929/1421. Its cycle 0
(`rootless-cognition-cycle-8d8618a0a8d14e8b916f`, source revision
`825048e13ec43a34cb6e79b410890e704784a7d8`) completed with acquisition
condition counts `[0, 0, 0]`. It also failed the threshold-8 baseline gate,
so transfer was skipped. Its cycle-result SHA-256 is
`32e180fd88b6669d9d983bb01ca13e7225df26ce137c485e6850d1ecc8660fec`.
Cycle 1 (`rootless-cognition-cycle-26c43d409f1d4332a674`) did not complete;
recovery stopped at `synthetic_pre_action_cognition` with
`recovered_tick_record_conflict` and no cycle-result. Its failure-record
SHA-256 is
`204056545737aa44f0870b8e865cc64a52427a19c25afbb89761d298afaf722b`.

These cycle-0 results show that neither run cleared the preregistered
baseline-competence gate; they do not score transfer. The cycle-1 failures are
execution/recovery integrity failures, not model-performance observations.
Different source revisions and seeds prevent treating the two campaigns as a
controlled replication. Together they motivate preserving cycle artifacts and
checking recovery integrity, but establish no durable learning, transfer,
history use, or developmental improvement.

A read-only [cycle-recovery inspector](../../tools/inspect_developmental_cycle_recovery.py)
was added to make these integrity states auditable without inference. It
prints identifiers and digests, never model output, and writes no cycle data.
The inspector verified both companion-run digests, each decision-to-receipt
ID/digest link, and each receipt output digest and byte count. It separates
three response-digest cases: direct receipt matches, the expected
`INVALID_EXPERIMENTAL_RESPONSE` marker for rejected output, and a validated
response changed by a governed normalization.

In the first incomplete cycle, decision index 1 of
`devexp-run-393f986dc50435aacac575e2` was marked validated and normalized as
`present_condition_requires_fresh_cited_current_evidence`. Its response
digest does not match the raw receipt response, so the normalized response
cannot be reconstructed from the receipt alone. Source revision
`dc349b9a2` applied the present-condition rewrite during controlled history
trials, including the withheld condition. Commit `ba099ceda` later made that
rewrite conditional on not being in a controlled intervention, preserving
direct response-to-receipt binding. The old run remains incomplete and
unqualified; the fix belongs in the source pins of any new frozen plan. A
separate companion run's rejected condition correctly binds its digest to the
`INVALID_EXPERIMENTAL_RESPONSE` marker rather than to raw model output.

For the second failure, the inspector found that the prior-cycle owner-feedback
record shares the recorded tick and exact snapshot identity with an already
persisted checkpoint whose record and receipt slots are empty. Commit
`dc349b9a2` (`Bind recovered feedback to companion tick`) adds recovery for
exactly this case: it attaches the feedback record and receipt only when the
checkpoint is empty and both snapshot identifiers match. A checkpoint bound
to another record, a nonempty receipt slot, or a different snapshot still
fails closed. Thus the saved error belongs to the older source revision
`825048e...`; the repair is present in source revision `dc349b9...`. The
inspector is supplemental custody tooling outside the pinned experiment
implementation. Its SHA-256 is
`d303d862c795ef8b0ab2cfb30a19054193adb63687bc51b02ad9b0b901765654`.
Invoke it as `python tools/inspect_developmental_cycle_recovery.py <cycle-root>`;
status 3 flags an unreconstructible normalized response digest, another
response-integrity mismatch, or an incompatible checkpoint. Status 0 means
none of those conditions was found in the inspected artifacts.


The preregistered two-cycle response-digest campaign completed its follow-up
probe in cycle `rootless-cognition-cycle-7e59c1f038f941dcbfbc`, using the
owner-feedback record from cycle `rootless-cognition-cycle-dbd9364284c7462dbe4f`.
The immutable follow-up result is
`rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-7e59c1f038f941dcbfbc/cycle-result.json`
(SHA-256 `a2dccde54d3d23e170b6b71e357ae8f99b9156ccd83e6d38b1e6d3b84679f4a3`).
Present and restored conditions selected the exact expected feedback record
and digest, but cited no history and abstained instead of returning the
preregistered answer. The withheld condition selected and cited no history as
expected, but answered instead of abstaining. Matched non-history inputs and
present/restored prompt restoration passed. Therefore the probe did not qualify
as history-conditioned feedback recall. It does not demonstrate model use and establishes no
learning, durable capability improvement, transfer, model-independent
continuity, or causal self-development. Those claims still require repeated,
held-out outcome evidence.

That completed result uses the v1 score serialization, whose
`delivery_verified` field only compared history citations with the expected
record IDs; it did not establish that content was delivered to or used by the
model. The current v2 score serialization reports selection, citation,
response, decision-validation, and condition-criterion assessments
separately.
The condition_criteria_met flag reports whether all per-condition
checks pass together; it is not a response-only score. A criterion match
records only that the observed response, citation, and selection match the
protocol. The scorer requires an explicit decision_validation_status value of
validated; a missing status fails the criterion.
It does not establish that the model cognitively used the record or
that the record caused the response. These labels are diagnostic
decompositions of the same frozen protocol criteria and do not retroactively
change the preregistered result.

The v25 prompt-only trial remains useful evidence that the instruction digest
changed while the model output did not. It does not test whether retained
owner-verified failure feedback changes future reasoning, because that feedback
was not carried forward as a developmental-history input.

### Transfer gate interpretation for the prepared v14 plan

The preserved neutral v2 12-by-12 plan uses the rootless_integer_affine_transfer_novel_range_v8 task family and does not preregister a separate cross_range_history_enabled_competence outcome. In the runner, acquisition competence is gated at two-thirds of the acquisition probes: the threshold is ceil(2n/3), or 8 correct probes for 12. When that gate is not met, transfer is skipped. Such a cycle has no transfer observation and must be reported as **transfer not evaluated**, rather than as a negative transfer result or evidence that history did or did not help.

The optional history-enabled competence protocol is a distinct, score-bound outcome with its own source and target task-family requirements. A future plan seeking that outcome must preregister the compatible protocol and its source evidence before execution. The current frozen v14 plan remains unchanged and unstarted; no result from it is inferred here.

The recovery inspector now also reports the recorded source revision, worktree content status, and clean flag from each failure artifact. These fields help distinguish failures captured under different source revisions; they do not establish that a revision caused a failure. In the two inspected failures, the recorded revisions are dc349b9a2655b7b46e5a2a0b5ea3fb3f89b7c409 and 825048e13ec43a34cb6e79b410890e704784a7d8; both artifacts report complete, clean source snapshots.

### Confidence audit evidence integrity

The CPU-only campaign confidence auditor v6 recomputes each acquisition-run digest and every selected developmental-record digest and identity before summarizing confidence or comparing retained task-family mappings. It fails closed if a selected record claims current truth, authority, policy, or canonical explicit-user-retention status. It also requires the campaign audit to verify append-only history, seed, runtime-admission, and cognition-recovery chains, and binds each planned cycle to that audit's source-run ID and digest. The transfer-precondition snapshot-chain status is reported separately because this diagnostic scores acquisition only. Schema v6 exposes the chain checks, selected-record integrity counts, verified abstention contract, and verified aggregate score status. These checks establish artifact integrity, not model attention, calibration, or learning.

### Saved confidence-audit finding

The v3 auditor was run against the completed two-cycle campaign `rootless-history-campaign-91a0cb4f42be41c19d11` (plan v8, wide-range v7). It found 18 maximum-confidence answers, of which 12 were correct and six incorrect, with a normalized mean Brier score of 0.333333. The v6 re-audit verified both cycle-bound source-run links, all required campaign chains, all seven selected-history record digests and postures, the score-v6 abstention representation, and aggregate status/correctness bindings; the transfer-precondition snapshot chain is true for this campaign. The score result is a small, protocol-specific confidence-saturation observation, not a general calibration estimate.

In cycle `rootless-cognition-cycle-64e9e8a2bb1b4b6995f7`, all three conditions scored 3/3 and the matched outcomes were identical. In cycle `rootless-cognition-cycle-3f1cd7832e9a4ba7aa11`, history-present scored 0/3, history-withheld scored 3/3, and history-restored scored 0/3. The selected-history mapping relation was incomplete in that cycle. These condition differences are descriptive associations under this small plan; they do not establish that history caused the performance change. The v3 report continues to claim no model attention, calibration, learning, or authority.

The historical v3 report is `artifacts/experiments/rootless-history-campaign-91a0cb4f42be41c19d11/confidence_diagnostic_v3.json`, digest `f0a094263d7e03c8b4ae7e45f1f1d23397a2a87b3dbbe3a06cc0035696d497fb`. The v4 and v5 re-audits remain available as historical reports. The current v6 re-audit is `artifacts/experiments/rootless-history-campaign-91a0cb4f42be41c19d11/confidence_diagnostic_v6.json`, digest `32a383e004b493e4b66b7f676dbc61d2f57ec0347357c4848e289b948ccdb9fd`.

### Independent receipt-to-score audit for the v1 recall result

The CPU-only auditor `tools/audit_cross_cycle_recall_receipts.py` independently bound the completed v1 follow-up result to its pinned protocol, opened the three referenced inference receipts, recomputed each receipt semantic digest and ID, recomputed output and response digests, checked UTF-8 output sizes, and compared parsed fields with both protocol criteria and score rows. The protocol and all receipt identity, status, digest, and score-link checks passed. All three outputs failed the protocol's exact response and disposition criteria; present/restored also failed the required history citation, and withheld included a non-empty evidence list. This independently supports the recorded unqualified result without retaining raw responses. It does not show that retrieved history was cognitively used.

The report is `artifacts/experiments/ordinary-chat-retention-20261127/cross-cycle-v1-receipt-score-audit.json`, SHA-256 `b85acc70fae09fefdfad1a3de7b4e7e377ce20b437011c45f1f3f7dfb922d038`. It binds result SHA-256 `a2dccde54d3d23e170b6b71e357ae8f99b9156ccd83e6d38b1e6d3b84679f4a3` and protocol SHA-256 `dc876a24153465ad632fc1893bd564192cbcf51a4cc5654728b7081d99174b60`. Raw prompts and outputs are excluded from the report.

### Neutral v2 pre-run digest custody

The digest-only record `artifacts/experiments/ordinary-chat-retention-20261127/neutral-v2-pre-run-digest-attestation.json` binds the neutral v2 campaign plan, its protocol, and the private mode-0600 run card before any cycle directory exists. The record leaves `preregistration_timing_independently_attested` false. Its GitHub commit timestamp provides an external before-run custody point for those digests; it does not prove when the plan was first drafted, independent authorship, or independent review. The run card remains prepared and requires a cycle-specific GPU confirmation at launch. Attestation-file SHA-256: `d8c1de1067c0ccdab68ef568a39b026a2f01c0701583bbe85b8e2fca9af2228c`.
### Repeatable pre-run attestation verification

`tools/verify_neutral_v2_pre_run_attestation.py` now rechecks the digest-only record against the private plan, protocol, and mode-0600 run card; confirms the attestation file is present byte-for-byte in its GitHub commit and reachable from the fetched remote snapshot ref; and checks the plan's cycle inventory, absent cycle roots, no-inference state, and per-cycle GPU gate. All 15 checks pass in `artifacts/experiments/ordinary-chat-retention-20261127/neutral-v2-pre-run-attestation-verification.json` (SHA-256 `d60996a9f2203f75ba3a6446c0de1464094489e6e415e3a68df374f01ae6ab2a`). The report also records verifier SHA-256 `275dee6370d31e8d3f8ce48e391301cbcdc3b90be3d3288d7b199a737b3f6bb7` and the snapshot ref head it checked. The check is strictly pre-run and keeps the original independent-timing flag false. It complements the separate 18-check frozen run-card verifier; it does not validate model behavior or establish learning.


### Runtime binding for the serialized history projection

The cognition binder now parses the exact JSON prompt string that is passed into the governed request and fails closed unless its developmental-history packets, historical embodiment reports, and selection metadata match the constructed context. It adds a receipt-bound `sentientos.developmental_history_prompt_delivery_binding:v1` containing the prompt digest, a digest over those exact model-visible fields, delivered packet identities, selected identities, and bounded counts. It retains no raw prompt or history text and explicitly makes no authority or learning claim. This closes the instrumentation gap between retrieval custody and what the serialized request contained; it still cannot establish that the model attended to or used that content.

This code change is after the frozen neutral v2 launch snapshot. The prepared run card and its source pins remain unchanged, and no inference was started. A future campaign using this binding must be frozen and re-attested against the updated source before launch; the existing plan must not be treated as having measured this field. No Hermes/GPU inference was performed for this change.


The CPU-only receipt auditor now reports this field as `receipt_bound_not_recomputed`, `legacy_binding_not_recorded`, or `invalid`. It checks the binding's schema, prompt-digest agreement with the request and epistemic metadata, recomputed request digest and request ID, selected identity agreement with receipt upstream evidence, equality between delivered-packet and selected-record identity/digest sequences, packet/count consistency, and the no-retention/no-authority/no-learning posture. Since the receipt intentionally contains no history payload, the auditor does not claim to recompute the history-payload digest from the receipt; the receipt semantic digest binds the recorded binding metadata. Existing v1 audit findings remain unchanged and are correctly classified as legacy for this new field.


### Claim eligibility for the neutral 12-by-12 plan

The frozen neutral plan is schema v14 and targets `rootless_integer_affine_transfer_novel_range_v8`. It has no `cross_range_history_enabled_competence` field. The offline outcome verifier requires protocol v2, including score-digest binding and per-probe transitions, so this plan cannot produce that verifier's history-enabled competence outcome. Its 12-probe acquisition gate and 12 transfer probes remain useful performance measurements, but passing them alone does not prove durable learning, cross-range history-enabled competence, or a causal history effect.

A future campaign that seeks that specific claim must be separately planned before inference using the supported wide-range target family, an eligible score-bound low-range source history, the model identity recipe, the protocol-v2 field, and its independent preflight. It must receive fresh source pins and before-run digest custody. Do not retrofit the frozen neutral plan or treat its results as satisfying these conditions.

A read-only inventory of the neutral plan's exact cycle-0 history boundary confirmed the boundary digest and parsed all 22 JSON history files. It found zero files carrying the required low-range source-family label (six novel-range and two wide-range family files were present). The sanitized report is `artifacts/experiments/ordinary-chat-retention-20261127/cross-range-source-history-inventory-20261127.json` with inventory digest `sha256:0ad5f5eda4ff9c1bfad9bf2ac3800241ddb72a0f4e117a524c8d44c48bd52415`. This is a bounded family-presence inventory, not a receipt-level source eligibility audit; score-bound source runs remain unverified. The next empirical prerequisite is to produce and validate the low-range source history before preparing the wide-range target campaign.

### Transfer-history retrieval preflight follow-up (2026-11-27)

The retained cycle-21 failure artifact
[cycle-failure.json](../../../sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-20261127000100000021/cycle-failure.json), SHA-256 `513cd299664612091f0cf075c2e8f77be9addba57c3d11b4c070dd9056ad9743`, records a pre-inference history miss. Its required set had three records; present and restored selected the two source anchors but omitted `devrec-5b094c92d60f2f81b21a71f5`, the cycle's own acquisition record. The record and its completed writeback checkpoint were present in the retained store. The failure prompt was 22,748 characters under the then-bound 24,576-character limit. A read-only diagnostic audit verifies the missing-ID and digest-set consistency, reports one omission in both present and restored, and confirms `inference_performed=false`; it does not attest artifact origin.

The later [wide-range owner preview](../../../sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-owner-prompt-budget-cpu-replay-v2/runtime-owner-preview.json), SHA-256 `11d14b84f64ab888e61a4eba681a6186561b35f480ae66622edcf24cb6844790`, uses the same three record IDs. Both history-present and history-restored selected all three with matching digests at 26,618 characters under a 28,672-character limit; withheld selected none. Its owner-to-binder path was exercised, with inference, learning, and authority false. The read-only verifier confirmed the owner payload and flattened report digest (`520e17193ac73c3285bb37ca53fb9d52d99342861cc047bb33a9535b631e7ecd`); it also reports that the frozen plan's implementation pins no longer match current source and that report origin is unattested. This is a separate wide-range task preview, not a rerun of cycle 21, so it supports retrieval feasibility with the larger bound but does not isolate the bound change as the cause of the earlier miss or establish transfer or learning.

The failure writer now includes `missing_required_history_record_digests` alongside the union of missing IDs. The verifier accepts historical v2 diagnostics that omitted this redundant list by deriving the expected digests from the required ID/digest bindings; when the list is present it checks it exactly. The repaired verifier returned `status=verified` for cycle 21 and explicitly reported that the union digests were derived from those required bindings.
### Source-current cycle-23 owner preview (2026-11-27)

To replace the stale source pins in the earlier CPU preview, a new two-cycle
wide-range-v7 campaign plan was prepared from the retained cycle-21 history
boundary. The plan binds to the current 2,558-file experiment implementation
and verifies against current source. Its plan digest is
`033be132d29fbfb41bf20bb2e1c641772d38e276d489855e67763ad789db48d9`;
the initial history boundary digest is
`9c0adb1a1e8c82ff5f3c4e85a3e178f939248ab5404b854498e9cbd8c92a7f0d`.
The plan's independent preregistration-timing attestation remains false.

The cycle-23 CPU owner preflight selected and bound
`devrec-5b094c92d60f2f81b21a71f5`,
`devrec-f7ec4f22d15a8170e1579aaa`, and
`devrec-34400ec9c2d6771162a8e291`; its prompt measured 26,450 characters
under the current 28,672-character bound. A separate runtime-owner preview
then exercised the owner-to-binder path from a disposable copy of the retained
cycle state. Present and restored selected the same three records, each at
26,651 characters; withheld selected none at 13,931 characters. The preview
did not mutate owner state, invoke a model, establish learning, or grant
authority. It demonstrates current-source retrieval and prompt feasibility
for this planned transfer condition. Because the source and plan differ from
the historical failed run, it does not isolate the cause of cycle 21's omission
or establish that a larger prompt bound alone fixes it.

Evidence is retained under
`sentientos-data/rootless-experimental/cognition-goal-20261127/wide-range-source-current-v1/`:
the plan, `cycle23-owner-preflight.json` (SHA-256
`2d3b6ef3850d9f278d8d4f11ea855dc4974e91e2dcfe913e0d8fb8463d556e9e`),
and `cycle23-runtime-owner-preview.json` (SHA-256
`f309307935cb2d88b7c6e4a161380e77da7070e04d1c16b3d6cac4421d702d8d`).
The plan's Hermes identity recipe was derived from its existing manifest only;
no Hermes model was loaded and no GPU inference was performed.
### Same-source prompt-budget counterfactual

A paired CPU-only preview isolated the prompt limit while holding the current
plan, source, history boundary, task, and model identity fixed. At 28,672
characters, present/restored retained the acquisition record and both source
records at 26,651 characters. Changing only the preview limit to the historical
24,576 characters caused the owner/binder to retain the two source records and
drop `devrec-5b094c92d60f2f81b21a71f5`; the exact required-history binding
then failed before inference. This reproduces the cycle-21 failure mechanism
under current source and confirms that the wider bound is sufficient for this
specific transfer preview. The historical failure artifact records the same
omitted record and old bound. The later bound increase is in commit
`52bb52118`. The paired preview strengthens the prompt-budget explanation,
but does not establish that no other historical source or runtime difference
contributed.

The sanitized counterfactual is
`cycle23-runtime-owner-preview-limit24576.json`, SHA-256
`0ec47adcb6d5940053a4f2c766164e1335ee597d14bd27e4ebca5e4203322573`,
with audit digest
`sha256:186e94f0e113461680665df05a3088df21c556fe82ebba04f8b4fc7fe444c787`.
It contains record identities and digests only. Both sides are CPU-only,
state-isolated previews; inference, learning, and authority remain false.
### Reproducible verification for the prompt-budget pair

`tools/verify_rootless_runtime_owner_prompt_limit_counterfactual.py` verifies
the current implementation pins, common plan/cycle bindings, both prompt-limit
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
unestablished and the frozen plan's timing flag remains false. No inference
has run. See the [OpenTimestamps client documentation](https://github.com/opentimestamps/opentimestamps-client)
for its timestamp and confirmation workflow.

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
independent reconstruction report returned `status=verified`. No source run
has executed, so none of these opportunities is evidence of correctness or
source eligibility. Both private artifacts are in the campaign directory as
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

The replacement remains prepared and unrun. It has no model correctness
outcome and has not met source eligibility. No inference was performed,
independent preregistration timing remains unestablished, and no learning,
causal, or authority claim follows. Run cycle 0 only after GPU access is
available and the runner's per-cycle availability and utilization gates pass;
cycle 1 must wait for a verified cycle-0 history and recovery prefix.
