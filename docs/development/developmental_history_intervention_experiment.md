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
writebacks retain the resident-developmental-writeback prefix. When that
companion tick is already checkpointed without a history record, recovery may
attach this feedback record only if the checkpoint snapshot ID and digest
match; other record conflicts remain errors. This models the feedback append
as the durable writeback completing the existing cognition tick. The
controlled history trials retain the direct model response so its digest remains
bound to the invocation receipt. Serving-time freshness normalization continues
to apply to ordinary companion decisions; trial outcomes are measured without
that post-inference rewrite. The general historical cue also matches both the
forms previous and previously.

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
model identities. The updated run-card verifier SHA-256 is
`722df61a48bf4778100d09a0cef58184147e6a5ececbfd01598a753c84e9c2ec`. The
revised private `campaign-run-card-neutral-v2-12x12-rev2.json` binds
the task family, probe counts, and initial-history digest explicitly. It passed
all 18 checks, including the previous-card digest link, in the updated offline
run-card verifier; its mode-0600 SHA-256
is `67fb0e15870e4f4c63bc22bd9c04729c3ac389542a202253549ee29779624960`.
Both cycles remain `prepared_not_started`; no inference was performed, and
preregistration timing is not independently attested. This is only a stronger
measurement plan. Even a fully qualified neutral-query result would not show
durable learning, general transfer, or causal development.

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
`1a637b75945d0fee12674ff165e39d3f84ec31da65777e64a8ef2f4674f1d3a9`.
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
