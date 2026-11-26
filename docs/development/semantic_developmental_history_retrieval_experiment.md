# Semantic developmental-history retrieval experiment

## Purpose and claim boundary

Ordinary chat can now use the configured semantic-history embedder while
selecting previously admitted developmental records. This changes retrieval
availability; it does not show that semantic retrieval selects better records,
that a model uses selected records, or that experience improves later behavior.

This experiment separates those questions. It first measures retrieval against
independently labeled relevant records. Only if that gate passes should a
separate response experiment test whether the selected history changes scored
model behavior. Neither phase establishes durable learning or model-independent
cognitive continuity.

## Phase A: retrieval-only comparison

Freeze a completed-history corpus and its record digests before creating the
query set. The freeze also captures the configured semantic embedder model ID
and immutable revision, or records that semantic retrieval is unconfigured.
Include only records admitted by the developmental-history owner.
Do not alter, relabel, or regenerate records during the run. For each query,
independent reviewers assign every corpus record exactly one label: relevant,
inapplicable because its task scope, source-model applicability, or evidence
posture does not match, or neither. Adjudicators must not see which retriever
selected a record.

Use at least 60 distinct queries, split evenly among three preregistered
strata:

1. **Paraphrased experience:** the query asks about an admitted experience
   without reusing its distinctive wording.
2. **Lexical distractor:** a plausible record shares query terms but is not
   relevant, while a separate record is relevant.
3. **No applicable history:** no record should be applied to the query.

Run each query against the same frozen corpus, exact prompt budget, target-model
identity, and maximum record count in two conditions: the current deterministic
lexical policy and the pinned semantic-history policy. Use the same production
record projection and integrity checks in both conditions. The owner-side
`compare_ordinary_chat_developmental_history_retrieval` method builds both
contexts under one composition lock and binds their record references, policy
IDs, prompt-budget outcomes, target identity, question digest, and durable
history-state digest in one report. The report records the configured semantic
embedder model and revision; the semantic retrieval-policy ID binds the runtime
embedder identity and selection-input digest when semantic encoding succeeds.
Configured identity alone does not prove that encoding succeeded. New v5
comparison reports bind `history_state_digest` to the frozen durable
record-and-receipt inventory; legacy v3/v4 reports retain their original
interpretation. Reports also bind a fixed `semantic_attempt_status` such as
`encoder_queue_timeout`, `model_unavailable`, `encoded_vector_shape_invalid`,
or `available`; exception text is never included. The paired verifier rechecks
that status, report digest, condition order, history-state digest,
record-digest shapes, and selected / omitted prefix partition before a report
is accepted. Empty outcomes retain the policy ID and distinguish no retrieved
records from retrieved records that could not fit the prompt budget.
It invokes no generative model; the semantic condition may invoke the configured
embedder and update its derived-vector cache. Save the query, corpus manifest,
embedder identity and revision, exact comparison report, and independent labels.
The report exposes the successful runtime embedder identity digest and the
digest of the cached index entries used for selection, separately from the
configured model ID and revision. The batch uses one shared cache tick so its
own writes stay invisible to later queries; it rejects reports with different
successful runtime identities or cache snapshots before persisting comparison
artifacts. This prevents within-batch query order from changing the cache
available to later questions while preserving question-specific history
exclusion and candidate sampling. Per-query lexical fallback remains visible
in each report. The comparison obtains identity, attempt status, and
cache-snapshot provenance from the exact semantic selection call; on lexical
fallback, identity and snapshot remain absent while the bounded fallback cause
is retained. Legacy v3 reports remain readable. Preserve per-query results and do not
pool repeated paraphrases of the same
source experience as independent examples.

`DevelopmentalExperimentStore.run_retrieval_comparison_batch` accepts 60 to
255 distinct queries in multiples of three, invokes the owner comparison for
each, rejects a batch if the history-state digest changes during collection,
persists each verified report, and publishes a cohort manifest linking the
immutable artifact IDs and digests. Cohort reload reopens and verifies every
referenced comparison. First call `persist_retrieval_corpus_freeze(owner=...)`
and record its immutable ID. Construct queries only after that freeze, then
persist them with `persist_retrieval_query_set(corpus_freeze_id=...,
questions=..., strata=..., source_experience_record_ids=...)`, with at least
20 queries assigned to each preregistered stratum. Prefer one distinct frozen
history record ID per query. The v7 query set verifies each ID against the
corpus freeze and derives the sampling-unit digest from the exact record ID and
digest. Its v7 adjudication packet withholds both record IDs and derived unit
digests; exposing the digest beside the corpus inventory would let reviewers
recompute the source-record mapping. At scoring, the preregistered
source record must be consensus-labeled relevant for paraphrased-experience and
lexical-distractor queries. For legacy v6 query sets, an externally supplied
unique source-experience digest remains accepted and retains its weaker
provenance posture. New record-bound query sets use gate v12 with
adjudication rubric v5; digest-bound query sets use gate v11. Gate v7 remains supported for historical protocols;
record IDs and derived sampling digests stay private to the scorer. Record identity does not by itself authenticate that two
records are independent experiences. The query-set artifact carries the embedder identity from the prior
freeze and binds the exact prompt
budget, gate thresholds, confidence level, bootstrap sample count, and
adjudication-rubric digest before retrieval results exist. Gate v8 additionally
counts a query as a false inclusion whenever either retriever selects any
record not labeled relevant, including ordinary “neither” labels. It reports
paired query-level rates and confidence intervals separately for lexical
distractors and no-applicable-history queries, and requires the upper
confidence bound and mean paired increase to stay within the preregistered
limit. The report also exposes each condition's rate. Earlier gate versions retain their historical inapplicability metric.
The score artifact schema advances to v12 for this output. The batch runner
accepts the immutable `query_set_id`; it checks the current owner inventory and
embedder configuration against the prior freeze before accepting the resulting
cohort. It performs that check before starting any query comparisons, so a
stale corpus or changed embedder configuration is rejected before an embedder
can be invoked. It repeats the inventory check afterward to detect history
changes during collection. The cohort binds both preregistration artifacts.
Calling the batch runner may invoke the configured embedder; it never invokes
a generative model.

After a cohort is persisted, create the reviewer-facing input with
`build_retrieval_adjudication_packet(cohort_id)`. New v8 packets contain the
original queries, their bound digests, complete corpus record references, and
the target-model identity bound at preregistration. They exclude retrieval
selections, preregistered strata, and source-experience bindings. Earlier v5-v7
packets remain readable with their historical fields. The v8 packet uses
adjudication rubric v5, which does not disclose strata or ask reviewers to
provide source-experience metadata. Reviewers judge
each query-record pair without retrieval outcomes; mark relevance only when the
record directly bears on the query and its scope, model applicability, and
evidence posture permit use, assessing model applicability against the packet's
target identity. When that identity is unbound, they must not assume same-model
applicability. Mark inapplicability only for an explicit qualifier mismatch;
ordinary irrelevance is not inapplicability. Reviewer and consensus rows for
v8 carry no stratum, and the labeler does not enforce a relevance pattern from
the hidden stratum. After review and consensus are sealed, the command binds
the private strata and source metadata from the cohort and query set. The
scorer preserves mismatches as evidence instead of rejecting labels for
disagreeing with the preregistration. The [adjudication packet JSON
Schema](semantic_history_retrieval_adjudication_packet.schema.json) defines
the new v8 reviewer-facing structure and excludes strata, source record IDs,
and source-unit digests. Runtime checks also verify canonical digests, ordering,
uniqueness, and balance.
Reviewers can inspect one record at a time through the owner's read-only
`retrieval_adjudication_record(cohort_id=..., record_id=...)` resolver. It checks
that the ID and digest are in the cohort manifest, then returns the bounded
production history projection with no retrieval-condition outcomes. The packet
itself is content-digested and does not expose which
records either condition selected. Do not give reviewers the cohort artifact
or comparison artifacts while they assign relevance labels. The annotation
set records this packet's digest. Each query row labels every frozen corpus
record exactly once as relevant, inapplicable, or neither, in manifest order.
The sealer and scorer verify a complete digest-matching partition of the frozen
manifest, so omitted records cannot silently disappear from the recall
denominator. This structural check does not prove a reviewer inspected each
record or assigned the correct label. Freeze a corpus small enough for
reviewers to inspect exhaustively; sampling the inventory does not support a
complete-corpus recall estimate.
Seal completed per-query labels with
`make_retrieval_relevance_annotations(packet=..., adjudication_procedure_digest=...,
annotations=..., independent_reviewers=..., blind_consensus=True)`, passing
`packet["adjudication_procedure"]["procedure_digest"]`. It binds the cohort,
history state, corpus, and packet
digests and rejects rows that do not follow the packet's query order. The
consensus annotation row for a v6 packet must copy that query's
`source_experience_digest` exactly from the blinded packet. Do not assign a new
digest during consensus. Record-bound v7 packets omit that field; the scorer
joins the source-unit digest from the private preregistered query set after
review labels are sealed. Legacy v5 packets retain their post-run assertion
field. The packet includes the fixed adjudication procedure and its digest; the
scorer checks both against the sealed annotation artifact.
Reviewer-template, annotation-sealer, query-set, and cohort validation also
check that persisted schema tags are strings before testing membership in the
accepted schema set, so malformed structured values fail as invalid artifacts
instead of leaking an unhashable-value exception.
The annotation contract requires two distinct reviewer digests, each reviewer's
complete ordered query labels, and a blind-consensus assertion. The scorer
recomputes exact agreement over relevant and inapplicable record sets and checks
reviewer labels against the frozen corpus; the evaluation artifact reports
agreement counts and rates overall and for each preregistered stratum. Consensus
labels remain the labels used for retrieval
metrics, while the initial submissions preserve disagreements.
The artifact also reports how many initial disagreements occurred and whether
each consensus label matches reviewer A, reviewer B, or neither. If both
reviewers initially agree, the sealer and scorer require consensus to preserve
that label.

Each `independent_reviewers` entry passed to the sealing helper has a unique
64-character lowercase SHA-256 reviewer digest and an `annotations` array in
packet order. Each reviewer row carries `question_digest`, `stratum`,
`reviewed_corpus_manifest_digest`, and `record_labels`. The latter is a
manifest-ordered array of `{record_id, record_digest, label}` entries, with
exactly one of `relevant`, `inapplicable`, or `neither` for every corpus record.
The helper rejects incomplete, duplicated, reordered, digest-mismatched
partitions. For v8, the sealer preserves labels that conflict with hidden strata; legacy packets retain their version-specific checks. It caps sealed annotations at 2 MiB, leaving
space for the corpus and evaluation data inside the store's 4 MiB artifact
limit.
For command-line sealing, use the packet and procedure digests emitted with the
templates at the top level as `adjudication_packet_digest` and
`adjudication_procedure_digest`. Put the completed consensus array under
`annotations`. Each `independent_reviewers` entry must wrap a completed
`submission` with the same two digests. Set `blind_consensus` only after the
independent reviews are complete and disagreements have been resolved without
retrieval outcomes. The `seal-annotations` command rebuilds the packet from the
cohort and rejects mismatched or missing bindings before invoking the annotation
sealer. The expected input structure is specified in the
[review-submission JSON Schema](semantic_history_retrieval_review_submission.schema.json).
Schema validation does not replace the command's packet binding, reviewer
distinctness, query-order, or exhaustive manifest checks. The resulting JSON is
ready for `score`.

Reviewer digests are pseudonymous bindings, not authenticated identities.
Blindness, independent review, record inspection, and consensus remain external
process attestations. Agreement measures exact label-set agreement, not
correctness or calibration. These fields and digests do not prove that reviewers
followed the procedure. Preserve the blinded packet and reviewer submissions
with the experiment record.

For legacy v5 query sets, `source_experience_digest` is supplied with the
post-run consensus annotations and remains an unbound external assertion. New
v6 query sets bind one unique source-experience-group digest per query before
the retrieval run; v7 query sets additionally derive those digests from exact
frozen record references and check relevant labels at scoring without exposing
the digests to reviewers. Their v7 adjudication packet uses rubric v4 and their
sealed annotation schema is v8. The paired
bootstrap resamples query rows, so its interval remains conditional on
independence between source records and does not establish population
uncertainty. Evaluation schema v10 reports exact frozen-record reference
verification separately from consensus relevance status and from independence,
which remains unverified. For no-applicable-history queries it records relevance as
`not_applicable`; it does not treat corpus membership as a relevance result. A
numerical pass remains conditional on the independence assumption.
A numerically passing retrieval gate is labeled
`retrieval_gate_passed_conditional_on_unverified_source_independence`; it does
not qualify as a plain retrieval-gate pass for new downstream ordinary-chat
intervention protocols. Legacy v8 evaluation artifacts retain their historical
projection when reloaded.

The operator entry point separates CPU-only preparation and scoring from the
embedder-capable retrieval run:

```text
python scripts/evaluate_semantic_history_retrieval.py freeze --config <cognition-config> --serving-config <serving-config>
python scripts/evaluate_semantic_history_retrieval.py queries --state-root <state-root> --corpus-freeze-id <freeze-id> --query-set <questions-strata-and-source-record-ids-json> --max-input-chars 8000
python scripts/evaluate_semantic_history_retrieval.py run --config <cognition-config> --serving-config <serving-config> --query-set-id <query-set-id> --max-input-chars 8000
python scripts/evaluate_semantic_history_retrieval.py packet --state-root <state-root> --cohort-id <cohort-id>
python scripts/evaluate_semantic_history_retrieval.py record --config <cognition-config> --serving-config <serving-config> --cohort-id <cohort-id> --record-id <record-id>
python scripts/evaluate_semantic_history_retrieval.py review-pair --config <cognition-config> --serving-config <serving-config> --cohort-id <cohort-id> --question-digest <question-sha256> --record-id <record-id>
python scripts/evaluate_semantic_history_retrieval.py review-template --state-root <state-root> --cohort-id <cohort-id> --reviewer-digest <reviewer-sha256>
python scripts/evaluate_semantic_history_retrieval.py consensus-template --state-root <state-root> --cohort-id <cohort-id>
python scripts/evaluate_semantic_history_retrieval.py assemble-reviews --state-root <state-root> --cohort-id <cohort-id> --consensus <completed-consensus-json> --reviewer-a <completed-review-a-json> --reviewer-b <completed-review-b-json> --blind-consensus-confirmed
python scripts/evaluate_semantic_history_retrieval.py seal-annotations --state-root <state-root> --cohort-id <cohort-id> --reviews <review-submissions-json>
python scripts/evaluate_semantic_history_retrieval.py score --state-root <state-root> --cohort-id <cohort-id> --annotations <annotation-json>
```

The `freeze` command uses the configured resident owner and receipt verifier;
its invoker rejects inference. Normal owner entry may reconcile an interrupted
checkpoint before creating the freeze. The `queries` command expects a JSON
object with parallel `questions` and `strata` arrays and exactly one of
`source_experience_record_ids` or `source_experience_digests`. Prefer record
IDs from the frozen corpus: the command verifies each ID against that freeze
and derives its sampling-unit digest from the immutable record ID and digest.
The digest-only form remains available for legacy cohorts, but its source-unit
binding is externally asserted and has weaker provenance. An optional
`target_model_identity` object records the identity observed during
preregistration; omitting it explicitly binds an unbound target identity. The
command persists the balanced query set against the prior freeze. The input's
structural constraints are in
[the query-set JSON Schema](semantic_history_retrieval_query_set.schema.json);
the owner API also requires equal array lengths, a query count divisible by
three, and an equal count for each stratum. Both steps are CPU-only and invoke
neither model nor embedder. Query-set creation seals the chosen prompt budget;
the run command rejects a different value before comparison begins.
The `run` command rebuilds the resident owner, verifies the immutable query set
and prior corpus freeze, then persists and reload-verifies the paired retrieval
cohort. It does not invoke a generative model, but semantic retrieval may invoke
the configured embedder and update its derived cache; schedule it when that
resource is available. Serving configuration does not expose the currently
loaded model identity, so the query set binds an observed identity supplied
during preregistration or explicitly binds an unbound status;
the run command cannot change that choice. The identity digest does not
independently authenticate the observation. The command reports whether the
cohort has an identity binding.
The `packet` command prints only the blinded packet. The `record` command
resolves exactly one record from that cohort's frozen manifest to the bounded
production history projection. It verifies the record digest and emits no
retrieval-condition outcome. It requires the resident cognition and serving
configuration, may run owner startup reconciliation, and cannot invoke a
generative model (the CLI's invoker rejects inference). Treat its output as
review material for that record only; it is not current truth or authority.
`review-pair` resolves one query digest from the same blinded packet, combines
it with exactly one record returned by that verifier, and emits the exact
packet-bound rubric, its digests, and preregistered target-model applicability
context. For v8 it also omits the preregistered stratum and uses review-pair
schema v2; legacy packet schemas retain the v1 stratum field. All versions
exclude source-experience grouping digests and retrieval outcomes. Reviewers can
use it to inspect one query-record judgment at a time without manually matching
records to questions. The [review-pair JSON Schema](semantic_history_retrieval_review_pair.schema.json)
defines the v2 output and reuses the packet schema's fixed rubric definition.
For each reviewer, run
`review-template` with that reviewer's externally assigned 64-character
lowercase SHA-256 pseudonym. It prints a wrapper bound to the exact adjudication
packet and rubric digest, plus one ordered submission object with a row for
every query and every frozen corpus record; each label is `null` and must be
filled by the reviewer. This is a structure aid, not a label source or identity
attestation. The template builder verifies the packet digest and rubric and
recomputes every query digest from its question text and reconstructs the frozen
corpus-manifest digest from the packet's record refs and history-state digest.
It fails closed when these bindings disagree or its serialized size exceeds one
quarter of the annotation artifact limit. The annotation sealer independently
recomputes the same query and corpus bindings before accepting reviewer labels.
Keep reviewer files separate until both
independent submissions are complete. `consensus-template` prints an ordered
wrapper bound to the same packet and rubric digest with a consensus-row array;
every label is blank. For v6 packets it copies each source-experience digest
exactly from the packet. For record-bound v7 packets it omits the field, leaving
the mapping private to the scorer. For legacy v5 packets that field is `null`
and remains an external post-run assertion. Neither template
command claims that reviews or consensus have occurred. The `seal-annotations`
command accepts the completed consensus rows and two independent reviewer
submissions, binds them to the rebuilt packet and procedure digest, and prints
the sealed annotation artifact. `assemble-reviews` combines the three completed
files, verifies their packet and procedure digests, and runs the annotation
sealer's structural and consensus checks before emitting the combined input.
It requires `--blind-consensus-confirmed`, an operator assertion that cannot be
authenticated by the local software. Template generation, assembly, and
sealing are CPU-only and invoke neither a model nor an embedder. The `score`
command
reads the sealed annotation JSON, persists and reload-verifies the immutable
evaluation, then prints the gate, aggregate metrics, and machine-readable
sampling assumptions. These commands do not
invoke a generative model or embedder; `run` is the sole embedder-capable step.
Packet export and scoring are CPU-only as well.

### Measures and gate

Report exact agreement between the two independent reviewers alongside paired
relevant-record recall at the configured prompt cutoff, mean
reciprocal rank of the first relevant record, and the rate at which any
independently marked inapplicable record is selected. Report these metrics for
each stratum and overall, with paired confidence intervals. Also report queries
for which the two methods selected identical record sets and cases where
selection fell back to lexical behavior. Under v4, identical sets and identical
ranking order are counted separately; v3 retains its original ordered-list
interpretation of the identical-selection metric.

New query sets use retrieval-gate protocol v5. Its primary paraphrase-recall
comparison is common-k recall: for each query, both ranked lists are truncated
to the smaller selected-record count before recall is computed. When both
conditions select zero records, both receive zero recall, so those queries
remain in the paired estimate. V4 also reports common-k reciprocal rank, which
captures ordering quality when both methods select the same set. The report
retains full-selection recall and reciprocal rank, the common record count per
query, and each method's selected-record counts.
Stratum summaries include a paired query-bootstrap interval for the selected-
count difference. Full-selection results show performance under the actual prompt budget, while
common-k recall isolates ranking quality from differences in how many records
fit. The 10-point gain and paired
confidence-interval gate use common-k recall for v4 and v5. These gates also require
mean full-selection recall to be non-decreasing, so a ranking gain cannot hide
a loss under the actual prompt budget. The inapplicable-record gate continues
to use the full selected sets as a separate safety measure.
The v4 and v5 query-set digests bind the common-k truncation and zero-selection rules,
the separate set/order reporting contract, the exact per-stratum and per-metric
bootstrap seed offsets, and the percentile interval's floor-index rule.
Stored v3 query sets retain their original full-selection scoring. Evaluation
schema v10 records the query-row sampling assumption, preregistered-unit binding,
frozen source-record bindings, and per-query relevance status. Persisted v4 through
v9 evaluation artifacts remain verifiable through
the legacy projection that restores their original report shape.
Protocol v6 also derives its bootstrap seed from the immutable query-set digest,
which exists before retrieval outcomes or reviewer annotations. Repeated scoring
of that preregistered query set therefore uses the same resamples regardless of
cohort and annotation artifact digests. Protocols v3 through v5 retain their
historical cohort-and-annotation-derived seed when their stored evaluations
are reverified. V6 also enforces both the preregistered point-estimate ceiling
and the paired upper-confidence bound for false-inclusion increases in the
lexical-distractor and no-applicable-history strata; older protocols preserve
their original gate computation.
Protocol v5 also preregisters a maximum of zero semantic-to-lexical fallback
queries for qualification. V3 and v4 cohorts retain their historical gates;
v5 and v6 cohorts with any fallback remain visible for descriptive scoring but
cannot pass the retrieval gate. The fallback ceiling is included in the
immutable query-set evaluation protocol before retrieval begins.

Annotations bind each question digest, cohort and history-state digest, and the
frozen corpus-manifest digest. The owner-side batch runner captures a
`sentientos.developmental_history_corpus_manifest:v2` from the durable,
eligible writeback records and their receipts, and stores it in the cohort.
Its `history_state_digest` binds the durable writeback inventory (record and
receipt identities and digests), while the manifest lists the eligible record
subset after unsafe-record filtering. V1 manifests remain verifiable under
their original schema and digest; they are not reinterpreted as v2.
The machine-readable shape and version meanings are recorded in
`semantic_history_corpus_manifest.schema.json`; runtime verification also
enforces canonical record ordering, unique IDs, and the manifest digest.
`make_retrieval_corpus_manifest(...)` canonicalizes and validates the record
references. The scorer checks every record exposed by either retrieval
condition, and every relevant or inapplicable label, against this inventory,
including labeled records absent from retrieved candidates.
The evaluation artifact preserves the manifest with the annotations and
recomputes the score from both on reload. This establishes internal referential
consistency; it does not independently authenticate the owner or adjudicators.
Annotations label each query's stratum and use digests for
source-experience groups and relevant / inapplicable record references.
There must be at least 20
queries in each stratum, with no repeated source-experience group. The
`blinded_adjudication` field and adjudication-procedure digest record the
labeling claim; they do not independently authenticate the adjudicators or
prove that their labels are correct. Adjudicators determine relevance against
the frozen corpus; the scorer verifies record existence and digests against the
cohort-bound manifest and cross-checks records present in retrieved candidates. The
scorer emits per-query outcomes and paired
aggregate metrics. `DevelopmentalExperimentStore` persists the
annotation set and evaluation immutably; reload reruns scoring from the
referenced comparison cohort and rejects a mismatch.
The evaluation reports each stratum and overall, including identical selected
sets and queries where the semantic policy records lexical fallback. Under v5,
any fallback means the registered semantic policy was not applied to every
comparison, so retrieval scores remain descriptive and cannot qualify the
mixed batch.

The preregistered retrieval gate requires at least 80% exact agreement
between the two independent reviewers in each of the three strata. The scorer
recomputes each stratum's rate from the retained labels, so easy strata cannot
mask disagreement in another. This threshold is part of the sealed evaluation
protocol; failure or insufficient agreement in any stratum leaves the retrieval
gate unpassed, regardless of retrieval metrics.

Proceed to Phase B only if semantic retrieval improves paraphrased-experience
recall by at least 10 percentage points (common-k recall under v4 and v5; full-selection
recall under preserved v3), the paired 95% confidence interval for
that improvement excludes zero, v4/v5 mean full-selection recall does not
decrease, and the inapplicable-record rate does not rise
by more than 2 percentage points at the upper paired 95% confidence bound in
either the lexical-distractor or no-applicable-history stratum. A failed or inconclusive gate leaves the
production behavior unchanged and the Phase B claim untested. These thresholds
are a proposed pilot gate and are content-bound into the immutable query-set
artifact before the comparison batch can run. The artifact digest provides
integrity, not an external signature or proof of when an operator inspected
outputs.

## Phase B: response-effect experiment

After the retrieval thresholds pass, preregister a separate ordinary-chat history
intervention using the existing matched `history_present`, `history_withheld`,
and `history_restored` prompt conditions. Keep the current message, dialogue,
non-history prompt, serving-model identity, and generation configuration
matched. Present and restored must contain byte-identical selected history;
withheld must differ only by the developmental-history block. Counterbalance
condition order and bind each run to the selection and prompt digests.

For this semantic-retrieval response phase, call
`OrdinaryChatHistoryInterventionStore.prepare_intervention` with
`retrieval_evaluation_artifact_id=<Phase A evaluation artifact ID>`.
The v5 response protocol binds the evaluation, cohort, query-set, and
target-model digests, plus the explicit gate status and qualification posture;
preparation accepts a plain legacy gate pass or a numerically passing current
gate whose qualification is explicitly conditional on unverified source
independence. It rejects a failed/inconclusive gate, an unbound or mismatched target model,
and an exact task question already used in the retrieval query set. Protocol
reload and execution revalidate the linked immutable evaluation. The generic
ordinary-chat intervention remains usable without this linkage for experiments
that do not claim to follow Phase A.

Use a frozen task set with independently scored outcomes and enough held-out
items to avoid using retrieval-gate queries as response-evaluation examples.
Score correctness, abstention, and calibration separately. Blind scorers to
condition labels. Restoration agreement is a manipulation check, not evidence
of learning. Report the exact paired outcomes and confidence intervals; do not
infer generalization beyond the preregistered task set.

The conditional qualification remains bound through the immutable Phase A
evaluation digest. The Phase B trial is a separate held-out response probe and
must retain the source-independence limitation in its interpretation. Its own
scored result does not retroactively qualify Phase A's sampling assumptions.
The existing ordinary-chat intervention protocol and immutable result custody
can support the matched response phase. The new Phase A linkage makes its
prerequisite auditable; it does not guarantee semantic retrieval caused a
response difference. This document does not itself create a run, authorize
model calls, or establish that either phase has been performed.

## Phase C: durability and transfer

An immediate Phase B response difference would still show only that selected
history affected a response under that prompt condition. It would not show that
experience changed a retained strategy or later cognition. A separate Phase C
must test that distinction:

1. Freeze an acquisition task set and a disjoint delayed probe set before
   observing outcomes. Bind both sets, the acquisition evidence digests, the
   scoring rubric, and the exact software and model identities in an immutable
   preregistration.
2. Use matched acquisition groups with and without the relevant experience
   available. Keep task exposure and outcome feedback fixed, and record each
   independently scored outcome with the exact experience and feedback that
   preceded it. Do not treat exposure to a stored record as successful
   acquisition. Before opening the delayed phase, apply a preregistered
   withheld-history competence criterion to the acquisition control outcomes.
   Freeze its numeric minimum and denominator before inference. If the control
   misses the threshold, retain the acquisition evidence but classify delayed
   transfer as `baseline_competence_not_demonstrated`; do not interpret a
   delayed null as evidence that retained experience had no effect. Do not
   select or replace task instances using paired treatment outcomes.
3. After a preregistered delay, run the probe set with the developmental-history
   block absent. Include new surface forms and, where the claim requires it,
   structurally related held-out tasks. Score correctness, abstention, and
   calibration independently and blind to acquisition condition.
4. Compare delayed no-history outcomes against the preregistered control and
   acquisition baseline. Report per-task paired results and uncertainty; do not
   pool repeated variants of one source experience as independent evidence.
5. Preserve negative, null, and contradictory outcomes. Attribute any later
   change to a specific admitted experience, observed consequence, retained
   update, and changed decision path. A later answer that merely retrieves the
   acquisition record does not count as durable change.

Passing such a study could support a bounded claim of durable, task-specific
development under the tested conditions. Transfer, general learning, and
continuity across model replacement require separately preregistered probes.
The 2026-11-24 negative-guidance replication illustrates why response change
and competence must remain separate. Its three preregistered pairs produced
eight answer-or-abstention changes across nine probes, but both arms scored
0/9 correct. The CPU-only
[cross-report verification](../../artifacts/experiments/negative-guidance-prompt-preview-20261124/analysis_verification_v2.json)
independently reconciles answer/abstention coverage and correctness with the
primary outcomes while carrying the same-answer and different-answer totals
from the source report. This is evidence about that prompt intervention and
task set; it does not establish a Phase C baseline failure or a general model
limitation. It motivates preregistering a control-competence threshold for
each future Phase C task family before interpreting delayed nulls or positive
deltas. Phase C protocol v11 now binds this criterion before outcomes: it
records the withheld-history acquisition condition, exact acquisition task
digests, denominator, and minimum correct-probe count. The store seals an
assessment from persisted acquisition outcomes before any delayed-probe
attempt; a delayed attempt is rejected unless the withheld-history baseline
meets the preregistered minimum. Earlier protocol versions retain their
original digests and behavior. This gate makes an unqualified delayed result
ineligible for interpretation; it does not establish learning or make a
delayed experiment complete.

New calls to `make_durable_learning_protocol()` now default to v11, and the
public `PROTOCOL_SCHEMA` constant names that current version. A caller must
provide the v11 withheld-acquisition minimum; an omitted threshold fails
protocol construction. `PROTOCOL_SCHEMA_V8` remains available for explicitly
rebuilding legacy plans. This default prevents newly created protocols from
silently skipping the competence gate, while preserving verification of older
protocol digests.

The repository now implements Phase C preregistration in
`sentientos/durable_developmental_learning_experiment.py`. It freezes disjoint
acquisition and probe inputs, task commitments, retained-history state digest,
baseline history-state digest, exact target-experience digests, software and
serving identities, generation configuration, scoring-rubric and feedback
policy digests, matched exposure/feedback contract, blind scoring posture, a
per-task/per-condition prompt-digest matrix, and a minimum-delay rule in the
governed immutable experiment store. Reload
rebuilds and verifies the task sets and their disjointness. The protocol makes
feedback matching an outcome-record requirement; preregistering the policy does
not establish that the observed feedback was matched.
The versioned `NO_FEEDBACK_POLICY_DIGEST` supports an initial Phase C study
before any scored Phase C outcomes exist. Under that policy, both matched
acquisition conditions must receive no feedback; prompt construction, receipt
preflight, and outcome verification bind and verify the empty feedback set.
Scored-outcome policies still require nonempty, source-revalidated feedback.
This removes the bootstrap dependency on a completed scored study, but does not
test feedback effects or establish learning. Later feedback-bearing studies
should preregister a scored-outcome policy and keep the policy and exposure
matched across conditions. In acquisition outcomes,
`feedback_policy_execution_verified=true` means the preregistered policy was
checked: for the no-feedback policy it specifically means the empty feedback
set was verified, not that feedback was delivered.
Each phase requires at least two distinct tasks so the frozen schedule can
include both condition orders. Protocol v5 used a nonce-flipped alternation
over input task order. Protocol v6 assigns each task's order by sorting a
SHA-256 rank of the protocol nonce, phase, and task digest, then divides the
ranked tasks as evenly as possible between the two orders. This avoids tying
order assignment to the task list position. The deterministic schedule is
bound before outcomes and omitted from scorer task plans; the nonce is an
operator-supplied preregistration value, not an independently authenticated
random seed. This controls an order-allocation weakness but does not create
randomized population inference or establish adequate statistical power.
Verification retains v5 schedule reconstruction and recomputes the v6
assignment; both require each phase to contain both orders.
The protocol verifier summary reports the assignment strategy and, for each
phase, the available-first and withheld-first task counts, their difference,
and whether both orders are present. These counts are digest-derived schedule
facts; the report explicitly marks the nonce as not independently
authenticated.
The v21 outcome report includes a task-family transfer structure summary: it
lists declared family IDs shared by acquisition and delayed probes, phase-only
families, and tasks without family metadata. Probe inputs remain disjoint by
protocol verification. Shared labels describe fixture metadata only; they do
not establish task equivalence, transfer, or learning.
It also stratifies available-minus-withheld correctness and answered-accuracy
deltas by the preregistered first condition for each phase. These small-sample
descriptive strata can expose order-sensitive patterns, but they do not by
themselves identify carryover or establish a causal order effect.
The local store requires the exact protocol to be persisted before it will
journal an invocation attempt, persist an outcome or probe gate, or finalize an
evaluation. First-time protocol persistence rejects existing run records bound
to that protocol ID, preventing this store's records from being appended before
the preregistration. This enforces local ordering; it does not independently
attest the filesystem clock or custody.

For resident-backed studies, obtain the baseline digest from
`ResidentDevelopmentalLearningExperienceSource.baseline_history_state_digest`
before protocol creation. It reads the resident cognition owner's validated
persistent writeback inventory under the owner's composition lock, including
each completed record and reconciled receipt identity. This gives the frozen
baseline a concrete owner source; later outcome state digests still
require receipt-time binding and independent verification before they can
establish a retained update.

The current task oracle is the deterministic affine fixture used by the
existing model-replacement experiments. The module can seal digest-only outcome
records from supplied outputs and recompute their deterministic scores; its
outcome-set verifier checks matched feedback digests, paired acquisition and
delayed probes, consistent retained-state digests within each probe arm, and
the frozen minimum interval between receipt completion times. Feedback records
are now bound to the preregistered policy digest, and acquisition outcome
verification requires an injected feedback-policy verifier to re-resolve their
source references and content digest; without it, outcome verification fails
closed. `DurableLearningScoredOutcomeFeedbackVerifier` supplies one built-in
policy: it revalidates a delayed-probe outcome from another protocol in the
same task family, requires that outcome to be included in a reverified
persisted evaluation, and reconstructs feedback from its score classification.
The feedback source ID binds protocol, evaluation, and outcome identities; the
feedback content carries the evaluation digest alongside the task digest and
score. Recursive provenance is bounded per verification thread and cyclic
evaluation references fail closed. This ties injected feedback to the
completed scored record set without permitting mutually referencing protocols
to recurse indefinitely.
Scored-outcome feedback policy v2 exposes an allowlisted, answer-free
source-task context (family, probe inputs, answer format, and history
requirement), so later cognition can relate a score to a concrete prior task
instead of an opaque digest. It omits the public descriptor's free-form
question because some task families place synthetic answer examples in that
field. Before producing feedback, the verifier rejects any source probe input
that overlaps any target acquisition input; the prompt receives neither the
source model's output nor an answer key. Its instruction labels the score as
source-task evidence and says it does not establish transfer to the current
input. Policy v2 also carries source and target serving-model identity digests
and their exact same/different relation; the prompt labels that relation as
identity provenance, not evidence that behavior transfers or cognition matches.
Policy v3 additionally requires an exact source/target scoring-rubric digest
match and labels it as a rubric relation, not scorer independence. Policy v1
and v2 records retain their exact version-specific reconstruction behavior.
This makes feedback more interpretable while keeping cross-task use
experimentally qualified.
The canonical prompt builder includes an
explicit history field only for the relevant acquisition arm. Acquisition
`DurableLearningPromptGuard` callbacks verify record digests and exact prompt
bytes and capture `retained_state_snapshot_resolver=experience_source.current_history_state_snapshot`;
delayed-probe `DurableLearningProbeStartGuard` callbacks verify the exact
canonical prompt has no history or feedback field and capture that same
owner-resolved state digest at gate opening.
Those attestations are persisted with and checked against the invocation
receipt. Outcome creation and reload require an injected
invocation-receipt verifier to bind each event to the exact prompt and output
digests, model and generation identity, admitted status, fallback/truncation
posture, and receipt-digest-bound completion time. It emits per-probe
correctness deltas and a per-condition comparison of delayed retained-state
digests against the preregistered baseline. Those state digests are captured by
the pre-effect guard and bound into stored invocation receipt evidence.
Acquisition and delayed-probe outcomes must match the captured digest; delayed
outcomes must also match the probe-start gate. Each snapshot carries the exact
record and reconciled writeback-receipt identities; the evaluation reports
added, removed, or changed inventory entries per condition. This verifies
durable inventory change around the calls, but does not attribute a writeback
to an experience. It makes divergence and no-change outcomes visible without
turning either into a learning claim. That completion-to-completion
interval alone does not prove when the delayed probe invocation started; the
pre-effect guard now records a local start time, but that clock has no external
attestation. The full inventory snapshot evidence is capped at 56 KiB and
fails closed before inference if it exceeds that bound.

The protocol freezes the baseline inventory digest. Snapshot verification
recomputes that digest from the sorted record IDs, record digests, and
reconciled receipt IDs and digests. The acquisition pre-effect guard requires
the live snapshot to match the frozen digest before every acquisition call.
Consequently, the report's `baseline_record_refs` are the owner-verified
acquisition pre-effect references for that frozen baseline; delayed inventory
changes are compared against that same reference set. This proves inventory
identity at the guard boundary, not who authored each record or whether a
changed record altered a later decision.

To inspect experience-to-writeback lineage, construct the protocol store with
`DurableDevelopmentalLearningProtocolStore.with_cognition_owner(
state_root, invocation_receipt_verifier=receipt_verifier,
cognition_owner=cognition_owner)`. This factory binds attribution to the same
receipt verifier used by the store. The attribution verifier independently
re-verifies every acquisition outcome before using its score or feedback
lineage. It resolves every newly
appearing record through the resident writeback inventory and recovered
observation, then checks whether the persisted history selection includes a
frozen acquisition record. The evaluation reports this under
`history_conditioned_writeback_attribution`. A match proves that the owner
recorded a history-conditioned cognition writeback with that record in its
selected context. The owner also exposes the exact inference receipt and
output digest for the recovered source observation; the report records
whether both the receipt identity and output digest match a scored acquisition
outcome, with aggregate counts for both match levels. This distinguishes a
writeback sourced from an acquisition response from one merely selecting the
same history record. The v8 attribution record also reports whether the exact
source receipt and output digest belong to the available-history arm and its
verified exposure list includes the selected experience. That strengthens
exposure lineage without establishing attention, reliance, improvement, or
causation. When the source receipt resolves to a scored acquisition outcome,
the matched row now carries its score digest, score status, correctness/count
summary, Brier sufficient statistics when present, and preceding feedback
digests. Under rubric v5, outcome schema v6 additionally retains the exact
`source_id`/digest references from the receipt-verified prompt guard, and the
paired acquisition verifier requires both arms to expose the same feedback
references. The attribution reports these as verified feedback-reference
lineage for the scored source response. When the frozen policy is the
scored-outcome policy and the exact available-arm invocation matches the
writeback source, it separately marks scored-outcome feedback exposure to that
invocation as verified. This means prior scored feedback was present in the
receipt-bound prompt; it does not establish model attention, use, or benefit.
The outcome-set verifier recomputes this exposure summary from every verified
acquisition outcome and rejects attribution reports whose claim disagrees.
The attribution report counts matching writebacks with this exposure by
condition and across both conditions.
This displays the independently scored consequence
associated with the source response without implying that its score was
available before the writeback or caused the update. Under rubric v5, the source score time is
signed by the scorer and compared with the writeback record's receipt-bound
creation timestamp. The attribution verifier requires that timestamp to be
timezone-aware and normalizes it before comparison; malformed timestamps and
duplicate or malformed selected-record references fail closed. The report
calls this a local-clock ordering only: clock
skew is not externally resolved. Feedback exposure is established separately
from the scorer-time comparison, through the receipt-bound prompt and scored
outcome feedback policy. Older rubrics have no signed score time and report
the comparison as unavailable. For each matching writeback it records how many frozen experience
records were selected, their coverage fraction, and whether selection was
complete or partial. Condition summaries count complete and partial selections
and total selected records, making variable retrieval dose visible without
implying reliance or learning. Exposure-lineage and selection-coverage counts
are reported by condition alongside the receipt- and output-linked counts.
Reuse the same verifier configuration when reloading evaluations
and when the scored-outcome feedback verifier loads their source evaluation.

The repository now provides a receipt-verifier adapter over stored chat
invocation receipts, which validates the receipt timestamp as part of the
receipt digest. Its context resolver maps each task to a session and user
turn; the receipt verifier reads both turns from `ConversationSessionStore`, checks
that user text hashes to the frozen prompt digest, and verifies the assistant
turn follows the user turn and that its request ID, loaded model identity,
source-user-turn, and receipt linkage match. It passes the persisted assistant
text into the serving verifier to bind transcript output to the invocation
output digest. `DurableLearningProbeStartGuard` can be passed as the governed
invoker's `pre_effect_guard` or through
`ProductionServingInferenceController.generate`'s optional guard argument; it
verifies paired acquisition outcomes and fails closed until the configured
receipt-completion interval has elapsed. Acquisition calls must pass a
`DurableLearningPromptGuard` through the same callback argument to persist the
prompt-content evidence. For the available-history arm, the stored-chat
receipt verifier also requires `ResidentDevelopmentalLearningExperienceSource`
to re-resolve the selected record IDs and digests from the resident writeback
store and match the canonical packet digest. Use
`select_experience_records(question, target_model_identity)` before freezing the
protocol's acquisition digests, then `records_for_prompt` at execution; drift
in record identity or projected content fails closed. Configure the receipt
adapter with the active `ConversationSessionStore` as
`conversation_session_store`, `experience_source.verify_prompt_evidence`, and
`DurableLearningScoredOutcomeFeedbackVerifier` as its feedback verifier. This
policy exposes the evaluation and task digests plus score classification only;
it omits the raw answer and oracle answer. The report marks policy execution verified
only after source revalidation succeeds. For stored chat, pass
the probe guard's `gate_id`
as `caller_linkage["durable_learning_probe_gate_id"]` with the callback. That
ID is copied into top-level request linkage before invocation. The receipt
verifier requires that linkage. The guard returns its full gate
record; the governed invoker persists that record in a bounded owner-side
artifact bound to the final invocation receipt and request digests. Stored
receipt verification reloads that artifact, and the Phase C verifier requires
the exact gate ID and digest to match the delayed outcome. This connects the
pre-effect gate to the actual probe receipt within the local custody chain.
The production executor sends the canonical prompt directly to the serving
controller; `ConversationSessionDurableLearningContext` records user and
assistant turns for receipt recovery but does not add prior session turns to
that prompt. The receipt verifier binds the stored user text to the prompt
digest and the assistant transcript to the invocation output digest. Thus the
delayed probe's absent-history condition excludes both the explicit history
field and prior experiment dialogue in this serving path; the session provides
custody, not model context.
Assistant-turn persistence is retry-safe for a repeated recorder callback in
any process using the session store: the store searches by invocation receipt
ID and, under the session's file lock, returns the existing turn only when its
text, role, retention state, and complete receipt/task linkage match. It fails
closed on conflicting or duplicate matches. This closes the crash window
between transcript persistence and outcome persistence without creating a
second turn. The guarantee depends on all writers sharing the store's lock and
atomic publication boundary; it is not a claim about arbitrary external
writers that bypass the session store. Both ordinary and idempotent session
append paths reject active or loaded model identities whose required digests
are absent or mismatched, so malformed provenance cannot be newly published
through the store and valid identity evidence remains reload-verifiable.
There is a remaining experimental-design limit: protocol v6 freezes one
baseline history digest. Protocol v7 binds two distinct condition branch IDs,
but `DurableDevelopmentalLearningRunner` still owns one experience source and
one retained-state snapshot resolver. Its production
executor records turns but does not invoke the resident developmental writeback
path. The delayed-probe condition labels do not activate separate persistent
history branches; both canonical delayed prompts omit the history block. As a
result, v6 verifies history-free delayed calls and reports any observed state
changes, but it does not route to or manipulate isolated retained-state arms.
A writeback
that occurs outside the runner may be attributed to a source receipt, yet the
current protocol cannot show that the available and withheld arms developed
separate states or connect a particular consolidation step to each probe arm.
Until a later protocol binds cloned condition-specific baselines, routes
acquisition and delayed probes to isolated resident state/session branches, and
orchestrates receipt-attributed post-acquisition writeback before probing,
delayed paired scores are descriptive and are not a condition-specific durable
learning or transfer contrast. The protocol verifier reports this as
`retention_contrast_eligible=false`. The runner refuses acquisition and delayed
probe inference by default when this flag is false. An operator can explicitly
set `allow_descriptive_only_execution=True` to collect exposure-only records;
that override does not change eligibility or the report's claim posture.
The required successor is specified in the
[condition-isolated protocol design](durable_learning_condition_branch_design.md).
`DurableLearningProbeStartGuard` requires an `on_gate_opened` callback that
persists the gate and journals the invocation attempt before returning its
attempt ID. The gate and attempt are therefore immutable in the experiment
store before the model effect begins. A persistence failure or missing attempt
ID aborts the call. The acquisition prompt guard has the same required
attempt-journaling contract.
The outcome report distinguishes canonical prompt-content verification from
external timing attestation and exposes whether the injected feedback-policy
verification succeeded.
This path does not provide an externally signed clock. The repository has
`DurableDevelopmentalLearningRunner` for staged, resumable acquisition and
delayed-probe batches over an already persisted protocol. It verifies already
persisted outcomes, builds the frozen canonical prompts, passes the pre-effect guard and
linkage through an invocation executor, persists outcomes, opens and stores
each probe gate before inference, and can persist the final evaluation.
On restart, the runner enumerates outcomes stored for the protocol and phase,
revalidates their scores, receipts, attempt markers, and immutable identities,
then merges any caller-supplied outcomes only when they exactly match those
stored records. Delayed-probe execution also reloads the complete acquisition
set from that store when the caller omits it, and fully verifies the paired
set before opening or recovering any probe gate. Callers can therefore resume
with empty outcome sequences; recovery does not depend on retaining an
in-memory list. The store rejects
duplicate condition/task outcomes and malformed or conflicting persisted
records before reconciling unresolved attempts. Finalization uses the same
reloaded acquisition and probe records to build the complete evaluation;
caller-supplied rows are optional consistency checks and cannot omit or alter
stored evidence. Missing preregistered outcomes still fail the evaluation
completeness verifier. Outcome and evaluation readers also reload the frozen
protocol from the protocol store before trusting its artifacts. Probe-gate
writers and readers additionally require the supplied acquisition rows to
match the complete, reverified outcome set already persisted for that protocol;
the gate cannot be built from caller-only acquisition evidence. Unresolved
attempt enumeration applies the same stored-protocol requirement.
The runner requires a `condition_blind_scorer(task_plan, output,
output_digest)` callback. It receives the sealed fixture task and response,
but no phase, condition, history state, or experience records. It must return
the score and an Ed25519 attestation. Protocol v5 freezes the scorer public key
and scorer software digest; the scorer service checks its observed software
digest against that commitment. The signature binds protocol, task plan, output
digest, and score digest. The
experiment verifies that signature and recomputes the score from the
receipt-verified transcript text. Keep the private signing key in a separately
operated scorer process. The signature proves which key signed the result;
it does not by itself prove who operated that process or that its private key
was kept separate from the model runner. The scorer task plan omits the
condition order so it cannot identify an arm from the preregistered schedule.
The v26 report makes this distinction explicit: it records that the task-plan
schema omits phase, condition, and experience records, while operational
condition blinding and scorer-process separation remain unverified until the
separate scorer process and its custody are independently observed.
For confidence-scored selective family-suite tasks, the new v5 task contract requires
an integer confidence estimate from 0 to 10,000 basis points for each answered
probe and `null` confidence for abstentions. The independent scorer reports the
sum of squared probability errors and the number of answered probes, yielding a
Brier proper score over answered probes; abstention coverage remains a separate
metric. A Brier score alone is not a calibration diagnostic. The score and its
signature bind these confidence scores to the exact output.
Scoring-rubric v5 preregisters the ten-bin equal-width reliability method,
its 0–10,000 basis-point range, boundary rules, and exclusion of abstentions;
it also freezes the paired answered-probe Brier comparison and requires a
scorer-signed `scored_at` timestamp. The timestamp is the scorer's claimed UTC
wall-clock time, not an external timestamp attestation. Existing v3 and v4
protocols remain verifiable against their original rubric digests. The paired
metric is preregistered only under v4/v5; the timestamp is attested only under
v5. The paired score remains a descriptive shared-answer subset comparison,
not a standalone calibration or causal claim.
Older task contracts retain their original output format and produce no
confidence score. The outcome report shows expected and complete Brier pairs
separately for acquisition and delayed probes, with task family clusters
retaining the paired Brier deltas (negative deltas mean lower squared
probability error for the available-history arm). It also reports ten-bin
reliability summaries by phase and condition with sample counts and observed
accuracy; these are descriptive and include no uncertainty estimates. A
preregistered run and adequately powered reliability analysis are still needed
to support a calibration claim. The v26 evaluation also derives a paired
Brier delta over probe indices answered in both arms, with separate counts for
indices answered in only one arm. This avoids comparing arm means over
different probe subsets, while remaining conditional on the shared-answered
subset; the one-sided counts expose the abstention asymmetry. This derived
comparison remains descriptive; the report labels it preregistered under v4/v5
and exploratory under preserved v3 protocols. It is not an inferential test.
Construct the protocol with the scorer's canonical base64url Ed25519 public
key and software digest, project them with
`durable_learning_scorer_binding(protocol)`, then
instantiate `ConditionBlindEd25519DurableLearningScorer` in the scorer process
with that minimal binding, the rubric function, and private-key `sign` method.
The service must pass its independently computed digest as
`observed_scorer_software_digest` when constructing the scorer.
The scorer process receives no condition schedule. Expose its
`handle_rpc_request` through an authenticated IPC/RPC endpoint and wrap its
authenticated transport with
`ConditionBlindDurableLearningScorerRPCClient`; pass that client to
`DurableDevelopmentalLearningRunner`. The client sends a bounded request
without phase, condition, or history fields and the private key stays with
the scorer.
Each attestation covers the task plan digest, exact response digest, score
digest, protocol digest, and pinned signing key ID. Under v5, the scorer also
signs `scored_at`. New protocol creation should use
`DURABLE_LEARNING_SCORING_RUBRIC_DIGEST`, which identifies v5. The verifier
also accepts the preserved v3 and v4 digests for older protocols; arbitrary
rubric digests are rejected. The v5 scorer binding carries the rubric digest
so the scorer selects the timestamped attestation contract. The legacy
four-field binding remains valid for v3/v4 protocols, which continue to use
untimestamped v1 score attestations.
Outcome creation and later verification also reconstruct the exact assistant
text from the receipt-bound conversation transcript and recompute its score;
the outcome record omits response text, while the transcript remains its
durable source. The assistant transcript linkage also records protocol ID,
phase, condition, and task digest, which the receipt verifier cross-checks.
Evaluation reports record scorer signature verification and
continue to mark independent scorer custody unverified.
The stored-chat receipt verifier can preflight the complete feedback batch
against every acquisition task family before the first inference, avoiding a
partial run when a later task would reject the feedback. The runner also
resolves and freezes every missing acquisition prompt and history projection
before the first call, so stale experience on a later task cannot be
discovered only after earlier calls have run.
`ProductionServingDurableLearningExecutor` adapts that callback to
`ProductionServingInferenceController.generate`, returns the governed
invocation receipt identity and output, and rejects incomplete, truncated, or
fallback receipts. Its context resolver receives the exact canonical prompt,
persists it as a user turn, and returns that stored turn record; the adapter
checks its ID, role, text, and canonical text digest. It must bind caller
`chat_service` and canonical `chat:{session_id}:{user_turn_id}` correlation ID
to the ordinary chat caller linkage for a
real persisted user turn and provide a response recorder that commits the
assistant turn against the exact receipt before the runner stores the outcome;
optional budget and resource context can also be supplied. The adapter
validates the persisted assistant turn's user-turn and receipt linkage. The
`ConversationSessionDurableLearningContext` helper supplies that session-bound
context and transcript recorder for an existing active session. Pass its
`receipt_context` method to `LocalModelDurableLearningReceiptVerifier` as the
context resolver; it reconstructs the task-to-turn binding from the persisted
client-request digest after a process restart. The adapter rejects a reused
user-turn or correlation identity within one executor. This integration has
not been exercised against a live session.
`create_production_durable_learning_runtime(...)` now assembles the context,
stored-chat receipt verifier, protocol store, serving executor, and runner.
It requires experience-source and feedback verifiers plus the RPC scorer
client, and performs no inference or scorer call during construction.
Inside the pre-effect guard, after the retained-state check and probe-gate
validation, the runner writes an immutable attempt marker immediately before
the model effect. On resume, it first enumerates and validates unresolved
attempts. When the stored-chat receipt verifier can recover exactly one
assistant turn for the deterministic user turn, it revalidates the governed
invocation receipt and pre-effect evidence, recomputes the score, and persists
the outcome without issuing another model call. Reconstructed outcomes carry
`outcome_reconstruction_posture=reconstructed_from_stored_receipt` in their
digest-bound v5 outcome record; outcomes sealed during the original call are
marked `sealed_from_live_invocation`. Each outcome also binds the deterministic
pre-effect attempt ID, and the store requires that exact immutable attempt
marker and prompt digest before persisting or loading the outcome. For delayed probes, recovery also
reloads and revalidates the persisted start gate. The reconstruction posture
is a digest-bound local sealing-path label, not an external attestation. If the transcript or receipt
is absent, ambiguous, or invalid, resume fails closed and does not replay the
effect; the operator must resolve that original invocation before continuing.
The v26 outcome-set report and evaluation also count live-sealed and
receipt-reconstructed outcomes by phase and condition, so recovery posture is
visible in the aggregate result as well as in each immutable outcome. The
current verifier also accepts stored v22 through v25 evaluations: it re-verifies
the full outcome evidence, projects away only fields introduced after each
version, then checks the original evaluation digest. New evaluations use v26.
The protocol
also cannot verify that prompt records came from the
system's persistent experience store unless that resolver is configured; it
cannot independently authenticate feedback or attribute a retained update to
the experience. The supplied fixture tasks contain private
oracle parameters and must remain in scoring custody. No Phase C results exist.
A durable-learning claim still requires live integration, verified exposure
and feedback custody, delayed independent results, and evidence linking the
change to a retained update.

Protocol verification now emits one answer-free v2 retention-gate diagnostic
that separates protocol requirements from runtime evidence. Current protocol
versions explicitly report the missing preregistered
`withheld_acquisition_competence_threshold`; all versions also require evidence
that this control competence gate was evaluated before delayed probes. This
requirement is driven by the verified negative-guidance result above, where
prompt response changes occurred without any correct answers. The v2 diagnostic
does not retrofit old protocols or qualify their outcomes. Branch custody, equal branch baselines,
distinct owners, sessions and non-overlapping state, session and writeback
roots, independently attested filesystem and conversation-store isolation, and
isolated probe state appear only for branch protocol versions. All versions list
post-acquisition writeback orchestration, delayed-probe oracle and answer-key
exclusion, runtime verification that delayed probes omit history, delayed
independent probe results, and attribution to a retained update. Strategy-probe
protocols additionally list the independent answer-example exclusion
attestation. The diagnostic is explicitly protocol-stage only: these
prerequisites require runtime evidence, and the protocol verifier does not
inspect persisted runtime artifacts. It never qualifies a run or changes the
existing ineligible gate. This keeps its inventory from implying that an
artifact is absent when the verifier has not looked for one.
The protocol store's `retention_evidence_inventory` read-only method separately
reloads and verifies the branch preflight, AppContainer profile pair, per-
condition profile and registry inventories and their baselines, and every paired
access-probe completion
when those artifacts exist. It also surfaces all verified runtime-setup
attempts and interruption records so retries are not hidden and a missing
completion is distinguishable from a run that never started. Discovery is
bounded and each returned artifact is reloaded through its verifier. Missing
dependencies are reported as not assessable; present artifacts are reported by
ID and digest. The method never promotes retention eligibility, even when the
local access matrix passes, because those artifacts do not attest enforced
process or filesystem isolation.

The sealed v6 protocol assigns per-task acquisition and probe order using the
nonce-derived balanced task-digest ranking described above. The runner follows
this schedule while the scorer's task plan omits it. Legacy v5 protocols retain
their nonce-seeded alternation. The schedule is fixed before outcomes exist and
hidden from the scorer, but it is not an independently attested randomization
and does not justify population-level causal inference.
Resume and full-outcome verification enforce the same schedule against
receipt-bound completion times, and reject a partial run that contains a later
arm while its scheduled first arm is absent.
The evaluation report exposes per-task paired acquisition and delayed-probe
scores, complete/incomplete counts, wins for each history condition, ties, and
observed minimum and maximum task deltas for both phases, plus the bound model,
software, scorer, and scoring-rubric digests. Acquisition scores
describe immediate performance under exposure; delayed probes describe
history-free transfer after the preregistered interval. These are descriptive
summaries; confidence intervals and population uncertainty are marked as not
computed, and no assumption that probes are independent is introduced.
For selective suite outcomes whose aggregate correctness is unknown because
some probes were abstained, the report also preserves paired per-task counts
of correct, answered, and abstained probes, along with their observed deltas.
These probe-count pairs are tracked separately from boolean correctness pairs;
they do not convert an abstention into an incorrect answer or establish a
population-level effect. Each pair also reports answered accuracy and answer
coverage for each condition and their deltas. Accuracy is undefined when a
condition abstains on every probe in that task. Paired rows retain the frozen
task-family identity and task schema version so repeated variants can be
recognized during analysis;
they remain task variants and are not independent observations by virtue of
appearing as separate rows. The outcome-set and evaluation report schemas are
`v15` to identify this expanded paired representation. Delayed-probe totals
distinguish task pairs with complete boolean correctness from pairs with
complete per-probe counts, and separately count probe input slots and the two
condition outputs represented by those complete metric pairs.
A family-cluster view
also groups rows by task family, task schema, and whether the task requires
family history. It reports the number of variants and descriptive mean paired
correctness, answered-accuracy, and coverage changes for each group. Tasks
without a declared family remain separate clusters. These cluster means are
descriptive and do not provide an inferential sample size or uncertainty
estimate. The current v26 report includes an equal-weight macro summary across declared
families, so families with more task variants cannot dominate the macro mean.
Ungrouped tasks are counted separately and excluded from that family macro.
Per-family direction counts use a consistent convention: positive means the
experience-available condition is favored, so Brier-score deltas are sign
reversed for direction counts while their reported raw deltas remain
available-minus-withheld. These counts remain descriptive and make no
independence or causal claim.

The injected executor receives keyword arguments `protocol`, `phase`,
`condition`, `task_digest`, `prompt`, `pre_effect_guard`, and
`caller_linkage`. It must return exactly `output`, `invocation_receipt_id`,
and `invocation_receipt_digest`. The staged call sequence is:

```python
acquisition = runner.run_acquisition(
    protocol=protocol, feedback_records=feedback_records)
probes = runner.run_delayed_probes(
    protocol=protocol, acquisition_outcomes=acquisition)
evaluation_id = runner.finalize(
    protocol=protocol, outcomes=[*acquisition, *probes])
```

## Phase D: developmental continuity across model replacement

The repository's [developmental model-replacement experiment](developmental_model_replacement_experiment.md)
already compares history-present and history-withheld responses from two distinct
model endpoints under one frozen causal context, then restores the original
endpoint. Its digest-level observations and objective per-probe scores can show
history association across those endpoints. It is not a live A-to-B serving
transition, and does not establish durable learning or continuity by itself.

A continuity study should follow, not substitute for, a qualifying Phase C
result. It must bind the Phase C acquisition and delayed-probe evidence, the
same retained developmental state, exact A/B model identities, runtime and
generation configuration, and the model-transition protocol. Repeat the
delayed probes without an injected history block under A, B, and restored A,
with the task set and scoring fixed before transition outcomes are observed.
Compare per-probe retention and transfer across endpoints and against the
pre-acquisition baseline. The existing frozen-context instrument can contribute
model-specific association and restoration measurements; a production
continuity claim additionally needs a separately authorized real serving
transition and evidence that the persistent system state, rather than a copied
prompt or model-specific cache, carried the relevant development.

This Phase D design is projected work. The current A→B→A experiment remains
useful evidence about history association, but it is not a completed durability,
transfer, production-transition, or model-independent continuity result.

## Current status

The production retrieval path, bounded semantic candidate selection, pinned
embedder identity, lexical fallback, ordinary-chat exposure binding, and
same-state owner-side comparison report are implemented. Verified immutable
artifact persistence, reload, and a bounded same-checkpoint query-set runner
are available through the developmental experiment store. A paired retrieval
scorer, immutable evaluation reload, and CPU-only adjudication/score CLI are
also implemented. Immutable corpus-freeze and balanced query-set artifacts
bind the configured embedder revision, exact prompt budget, evaluation gates,
experimental order, and strata before retrieval; the runner rejects drift
before invoking retrieval. The blinded packet carries the versioned relevance
and inapplicability rubric, and both the query set and scorer bind its exact
digest. Independent relevance labels and Phase A results are not yet
available. No
developmental-history semantic-retrieval quality or response-effect claim is
established.

## v8 blinded adjudication correction

The record-bound v7 workflow exposed `preregistered_stratum` to reviewers and required their relevance labels to match stratum expectations. That could steer judgments and made disagreement with the query design impossible to observe. New cohorts now emit v8 reviewer packets: query text and digests, the corpus manifest, target identity, and the v5 rubric remain visible, while strata and source-experience bindings are withheld. Reviewer and consensus templates omit strata, and the sealer no longer validates reviewer labels against the hidden stratum. After consensus, it binds private strata and source metadata from the cohort and query set. The scorer reports source-record relevance mismatches instead of rejecting them.

Gate v9/v11 are used for digest-bound units and gate v10/v12 for source-record-bound units; v11/v12 add finite-sample false-inclusion intervals. All four bind the stratum-blind v5 adjudication procedure. Sealed annotations use schema v9 and preserve independent review labels without stratum fields, while consensus rows receive strata only during sealing. Legacy v5-v8 packets, annotation schemas, and gate protocols remain readable with their historical behavior. This correction improves label independence but does not authenticate reviewers or establish retrieval quality; Phase A still requires external blinded labels and CPU-only scoring after those reviews exist.
Legacy packet reconstruction is selected from the cohort's frozen gate version: gates v9-v12 produce v8 packets, while prior cohorts rebuild their historical v5/v6/v7 query rows and rubric so packet digests remain stable for evaluation reload.

New query sets use gate v11 when source experiences are externally digest-bound
and gate v12 when they are bound to frozen source-record references. These
versions retain the v9/v10 adjudication and retrieval rules, while replacing
the false-inclusion percentile-bootstrap interval with a paired binary
Clopper–Pearson interval. For each paired query, semantic-only false selection
is an adverse discordance and lexical-only false selection is beneficial. The
interval subtracts Bonferroni-adjusted exact bounds on beneficial discordances
from bounds on adverse discordances. This avoids zero-width bootstrap intervals
when all paired outcomes match and gives a finite-sample risk-difference bound.
The existing paired query/source-independence assumption still applies, and
the interval does not estimate population uncertainty beyond that assumption.
Historical v3–v10 query sets retain their frozen percentile-bootstrap scoring.
The current design caps each stratum at 85 queries. With no adverse or
beneficial discordances, the v11/v12 95% interval's upper bound is about 5.0%,
so the 2% non-inferiority criterion cannot pass on an all-identical stratum at
that cap. Under this interval, at least 217 independent paired queries in that
stratum would be needed for a zero-discordance upper bound at or below 2%.
Thus a non-passing result with identical outcomes is inconclusive at the
current sample cap; the sample design or a preregistered evidence threshold
must change before such a result can certify non-inferiority.
For v11/v12, each safety metric also reports the zero-discordance reference
upper bound and whether that reference would meet its preregistered margin at
the observed query count; it is a design-precision diagnostic, not an observed
outcome or a replacement for the paired interval.

For v8 review results, the scorer now records per-query consistency with the preregistered stratum label expectations and aggregate mismatch counts by stratum. It does not reject or rewrite independent labels. The retrieval gate requires zero such mismatches, so disagreements remain visible and prevent a malformed query set from quietly qualifying. Evaluation schema v12 adds these diagnostics; reload projects v4-v11 artifacts back to their original schema and digest.
For source-record-bound query sets, the same diagnostics separately count when the preregistered source record is not judged relevant on positive-history strata. Those labels remain intact; the gate is unqualified until the query/source binding and stratum expectations both agree with the independent consensus.
The v12 `query_stratum_label_validation.preregistered_query_design_consistent` field describes only stratum and source-record consistency; it is not the overall retrieval gate result. Overall qualification remains in the evaluation's top-level `gate.status` and depends on the metric and reviewer-agreement criteria as well.

A read-only search of `/home/zombinator/.local/state` found no persisted retrieval query-set, cohort, or evaluation artifacts. Phase A therefore has no current local reviewer labels or scored retrieval results; the implementation and protocol are prepared, but retrieval quality remains unmeasured.


## Rootless corpus capacity check (2026-11-23)

The current source-bound rootless cognition plan freezes a 46-file history
boundary with 23 record files and 23 receipt files
([plan](../../artifacts/experiments/rootless-history-campaign-5bda38a8a0016b2f4825/plan_v1.json)).
The record-bound retrieval query-set contract requires at least 60 distinct
queries and a unique frozen source-record ID for every query. Therefore this
particular 23-record snapshot cannot supply a source-record-bound Phase A set;
it is short by at least 37 unique record IDs before relevance review begins.
Record uniqueness alone would not prove independent experiences. This is a
capacity finding for the inspected rootless snapshot, not a claim about any
separate production history corpus. Keep the record-bound gate and its sample
size intact; gather a larger eligible corpus before constructing reviewer
packets rather than weakening the evidence unit or treating repeated records as
independent queries.


## Stratum-blinding carry-forward correction (2026-11-23)

The packet builder had selected the blinded v8 reviewer packet for gates v9
and v10 but omitted v11 and v12, even though those protocols inherit the same
stratum-blind adjudication contracts and only change the finite-sample
false-inclusion interval. As a result, a v11/v12 packet could expose its
preregistered stratum. The builder now emits v8 for all four gates (v9-v12),
so the reviewer packet omits strata and source-record bindings as intended;
legacy gate behavior is unchanged.

The inspected local experiment stores contain no persisted retrieval cohorts
or review annotations. Any pre-fix v11/v12 annotations found in another store
must be treated as non-blinded and re-adjudicated under a newly built packet
before scoring; the corrected packet digest intentionally will not match a
packet that exposed strata. This correction restores the blinding boundary; it
does not create independent reviewer labels or establish retrieval quality.

### Live corpus availability recheck (2026-11-23)

A read-only inventory of `/home/zombinator/.local/state` found no persisted
semantic-retrieval query sets, cohorts, corpus manifests, or reviewer
submissions. The two live cognition-history directories present in that state
tree contain no `devrec-*.json` records; each contains only its writeback lock
file. The separately prepared source-bound rootless history snapshot contains
23 distinct record files.

A follow-up read-only audit inspected 54 archived rootless-cycle history
locations. The writeback controller's non-repairing `inspect_completed_records`
path verified record, receipt, and admission lineage in 47 stores; four stores
failed closed on missing or ambiguous admission evidence, and three had no
record directory. The 47 verified stores contain 71 unique record IDs without
digest conflicts, but the largest individual snapshot has 28 records. All 71
records contain selected fact payloads; their selected sources are embodiment
records with governed local-model transformation provenance. This is a narrow
experimental archive spread across separate historical states, not one live
history corpus. The union must not be treated as a production corpus or
silently merged. A multi-source corpus would need a frozen manifest that binds
each record to its originating admitted store and state digest before query
construction. Do not generate synthetic record references or repeat a record
to meet the minimum. No eligible source-bound retrieval cohort or independent
review annotations exist, and retrieval quality remains unmeasured.

The intermediate provenance contract is defined in
`semantic_history_federated_source_manifest.schema.json` and implemented by
`sentientos.federated_history_source_manifest`. Its builder accepts a private
stable origin key and an already validated single-store corpus manifest; it
derives an opaque source ID and copies only digest-bound record references.
The validator recomputes the federated digest and verifies every embedded
single-store corpus digest. `FederatedHistoryRecordResolver` accepts the
private origin-to-live-owner bindings and the production projection function.
For each requested `(source_id, record_id)`, it rechecks the owner's complete
current corpus and history-state digests before and after retrieving the
record, then returns an answer-free source-bound envelope. `resolve_many`
preserves reference order, limits each owner to its 16-record projection
bound, and checks each source once more after the batch. A state change or
record mismatch fails closed. The envelope includes a sampling-unit digest
over `(source_id, record_id, record_digest)`, so later query sets and
cluster-aware scoring can distinguish equal local IDs from separate stores.
`resolve_corpus(source_id=...)` enumerates that source's complete frozen
record set in batches no larger than the owner's 16-record retrieval bound;
it verifies the full corpus state around each batch and returns projections
without modifying the source. This supplies the record side of exhaustive
independent review.

Federated artifact digests now use the schema's explicit `sha256:<hex>` form.
The shared `local_model_authority.digest_payload` helper returns bare hex, so
the federated module adds the prefix at its typed-artifact boundary while
keeping opaque reviewer identifiers as bare 64-hex values. This was corrected
before any federated query or review cohort was frozen; all builders and
validators in this module use the same prefixed representation.
Each source entry
binds an opaque source ID to that store's verified history-state digest,
single-store corpus-manifest digest, and local record IDs/digests. The same
local record ID may occur in different stores; its identity in a federated
consumer is the pair `(source_id, record_id)`, never the record ID alone. The
federated digest must cover the canonical ordered source entries, including
all record bindings, and runtime validation must enforce sorted unique source
IDs and sorted unique record IDs within each source. The JSON schema checks
shape only; it does not verify admission lineage, source identity, or any
digest calculation.

This inventory is still deliberately not accepted by the existing retrieval
freeze or query-set APIs, which require one live owner and one reconciled
history state. A caller must reopen each origin as a verified owner and pass
the private origin-to-owner bindings to the resolver. Source IDs must be
derived from a stable origin identity and the private mapping from source IDs
to archive locations must remain outside published artifacts. A federated
comparison runner and persisted cohort format are still needed before an
archive retrieval run can be measured. No retrieval run or model invocation
was made for this implementation step.

The federated preregistration layer is implemented by
`make_federated_retrieval_query_set` and
`validate_federated_retrieval_query_set` in the same module, with shape
described by `federated_semantic_history_query_set.schema.json`. It requires
60–255 distinct questions, equal counts across the three existing strata,
and one unique, manifest-bound source record per question. Each reference
retains the full `(source_id, record_id, record_digest)` binding and its
source-qualified sampling-unit digest. Query-set digest and ID bind the full
question, strata, source, budget, and target-identity snapshot. The artifact
also binds a frozen v12-derived federated evaluation protocol and explicitly
states that no inference occurred and learning is not established.
The source binding and strata must remain hidden from independent reviewers
until scoring, following the existing blinded packet boundary. This query
artifact is not consumed by the single-owner runner and by itself does not
establish question relevance or retrieval quality.

`run_federated_retrieval_comparison` now consumes that frozen query set and a
live resolver. It resolves every source's complete corpus, verifies that the
result is an exact partition of the manifest's source-qualified records, and
passes the same globally ordered record union to the lexical and semantic
selector for each question. It does not merge per-source top-k results, which
would change global ranking. Each selector receives the frozen character
budget and a maximum selection count. Source inventories are checked before
and after the run; a changed source fails the operation. The runner emits the
existing digest-bound comparison artifact and uses explicit lexical fallback
only when the semantic selector returns `None`. It also enforces the
exhaustive review pair budget before reading the corpus.

`federated_ordinary_chat_retrieval.project_federated_candidate_record` and
`run_federated_ordinary_chat_comparison` provide the production-policy adapter.
The ordinary-chat path and adapter now share
`_ordinary_chat_history_search_document`, so both use the same weighted lesson
scope, feedback, and typed embodiment text. The adapter applies the current
overlap score, decision-polarity ordering, source-bound correction grouping,
recency fill, bounded semantic candidate sampler, cosine threshold, and CPU
embedder identity check over the global chronological union. Its policy ID is
explicitly federated, and its implementation digest binds the adapter, the
production cognition module, tokenization, and semantic embedding source.
It deliberately does not reuse the mutable per-owner semantic vector cache;
the preregistered comparison therefore measures fresh global-union selection.
The frozen query has no conversation-session context, so this run does not
claim to reproduce the elliptical-chat context fallback. These scoped
differences are part of the federated policy and must remain visible in any
result interpretation. The adapter rejects a target-model identity that does
not exactly match the identity and digest frozen in the query set.
It scores the ranked record selection before ordinary-chat prompt packing;
it now applies the shared ordinary-chat instruction and history packet builder,
then trims the ranked prefix against the frozen serialized-character budget.
Source-qualified IDs are included in both the packets and selection metadata.

The generic runner is orchestration, not evidence that an arbitrary supplied
selector reproduces production behavior. The ordinary-chat adapter provides
the first shared-policy global implementation and seals a source digest plus
its selection limit into the comparison. Its compatibility with the live
single-owner path has not yet been empirically compared on a frozen cohort;
the cacheless federated semantic path and absence of session context remain
explicit policy differences. No federated cohort, model invocation, or
retrieval-quality result was produced for this implementation step.

`scripts/run_federated_semantic_history_retrieval.py` provides `freeze-sources`,
`freeze-queries`, `review-packet`, `complete-review`, `consensus`, `score`, and `run` commands. Source bindings map each source ID to its
stable origin key and cognition and serving configs. `source_id` can be omitted
for the initial `freeze-sources` command; the command derives it from the
origin key. `run` requires the resulting IDs in the private bindings. Freezing
sources opens owners read-only and writes the validated source manifest without private
origins. The private binding file shape is defined in
`federated_semantic_history_private_source_bindings.schema.json` and is never
copied into the public artifact. `freeze-queries` accepts a query-spec object
with questions, strata,
source-experience references, input budget, and target model identity, then
seals the query set without inference. `run` opens the same owners through the
read-only experiment invoker, requires consistent semantic embedder
configuration, validates the comparison after the run, and writes only a new
output file. Private origin keys and local config paths are not copied into
published artifacts. Each output path must be new; existing files are not
overwritten. The query-spec input shape is defined in
`federated_semantic_history_query_spec.schema.json`; runtime validation still
enforces equal stratum counts and unique manifest-bound source records.
`review-packet` resolves the full frozen corpus once per source, rechecks all
source inventories, and writes a blinded exhaustive pair roster plus its
blank reviewer template. The bundle shape is defined by
`federated_semantic_history_reviewer_packet.schema.json`; pair content may
still reveal source identity.

`complete-review` accepts the private manifest and query-set paths for
validation while the reviewer can receive only the blinded packet. It checks
the packet against that frozen experiment, every pair digest, and
pair-to-template ordering before accepting the versioned labels in
`federated_semantic_history_review_labels.schema.json`. `consensus` and `score`
revalidate both reviewer packets against the frozen manifest and query set
before using their templates. Consensus requires the operator to explicitly
attest blind adjudication; score recomputes descriptive metrics from the full
artifact chain. These checks do not authenticate reviewer independence or
establish durable learning.

`FederatedHistoryRecordResolver.build_review_pair` creates one reviewer unit
from a validated query set and one resolved record. Its schema is
`federated_semantic_history_review_pair.schema.json`. The pair contains the
question, digest-bound record projection, and an opaque `frec-...` handle; it
omits source IDs, local record IDs, candidate IDs and digests,
source-experience bindings, strata, and retriever outcomes. Projection fields
carrying record, candidate, or store locators are removed structurally. Record content can still reveal its origin, so this is
selection-blind and locator-redacted, not a guarantee of source anonymity.
The pair builder now feeds an exhaustive annotation template and submission
validator; retrieval scoring remains outstanding.

`make_federated_retrieval_review_template` now accepts the complete set of
pair packets and requires exactly one pair for every query and every frozen
corpus record, with no duplicate or missing pair. It refuses rosters above
25,000 pairs so reviewers do not receive an unbounded annotation task. The
blank template is bound to ordered pair-packet digests and one opaque reviewer
digest. `complete_federated_retrieval_review_template` accepts one label per
slot from `relevant`, `inapplicable`, or `neither`, preserving the sealed
roster and emitting a digest-bound submission. The template and submission
schemas are `federated_semantic_history_review_template.schema.json` and
`federated_semantic_history_review_submission.schema.json`. These checks
establish exhaustive shape and binding only; reviewer independence and
retrieval scoring are not established.

`assemble_federated_retrieval_review_consensus` validates two completed
submissions against their separate templates, requires distinct reviewer and
adjudicator digests, and refuses a consensus that changes an initially agreed
label. It binds both original submission digests and preserves initial
exact-agreement counts/rates at both query and individual record-label levels,
per-question agreement, and all consensus labels. The matching validator recomputes
the consensus against both original submissions. Disagreements are left to the
supplied adjudicator; distinct digests and the operator's blind-consensus
attestation do not prove reviewer independence. Its output shape is defined
in `federated_semantic_history_review_consensus.schema.json`.

`score_federated_retrieval_comparison` now binds a source-qualified ordered
selection artifact to the federated query set and reviewed consensus. It
reports full and common-k recall, reciprocal rank, inapplicable and
nonrelevant selection indicators, fallback counts, preregistered source-record
relevance checks, per-stratum descriptive means, and query-row confidence
intervals from the protocol frozen in each query set. It rejects stale or
unknown selected-record digests and incomplete query-by-corpus labels. The
comparison artifact builder binds policy IDs and the retrieval implementation
digest. The query set now freezes the v12-derived federated protocol,
including its thresholds, bootstrap parameters, exact paired binary interval,
and adjudication rubric digest. Intervals are explicitly conditional on
unverified source and reviewer independence. The scorer reports whether those numeric
criteria are met, but its qualification remains conditional because source
and reviewer independence are unverified. It keeps learning unestablished.
`validate_federated_retrieval_score` recomputes the complete
score from the bound query, comparison, both reviewer submissions, and
consensus. The v2 scorer additionally requires the verified federated
experience-anchor audit (`--experience-anchor-audit`) and its saved
source replay. The `score` command takes `--cycle-parent`, `--experiment-root`,
and `--freeze-export`, reruns the anchor verifier against those current sources,
and binds the resulting verification digest into the score; a supplied
self-digested audit or verification receipt alone is insufficient. The scorer matches
every query's source record ID and digest to a typed run/event anchor, rejects two
query rows anchored to the same recorded event, and binds the audit digest and
per-query event-anchor digest into the score. This prevents distinct record
IDs from silently standing in for distinct recorded experiences. It does not
establish statistical independence or independent reviewer operation. See
`federated_semantic_history_retrieval_score.schema.json`.
The frozen 71-record corpus now has a source-replay receipt at
[`federated_experience_anchor_verification_v2.json`](../../artifacts/experiments/semantic-retrieval-capacity-20261123/federated_experience_anchor_verification_v2.json),
digest `sha256:1831dfcac72b23e4d817427aabdc175dc88569032dd146db6ab87df8e5fe30d0`.
The implementation and schemas parse cleanly, and the score CLI exposes the
required source-replay inputs. No federated query set or reviewed cohort exists yet,
so this scoring gate has not been exercised on a retrieval score.


### Finite-sample scoring carry-forward correction (2026-11-23)

A follow-up source audit found that v11/v12 scoring computed finite-sample
nonrelevant-selection summaries but did not emit the corresponding per-query
nonrelevant-selection indicators consumed by those summaries. The scorer now
uses one shared version set for those per-query indicators, aggregation,
qualification, and output fields. Gates v11/v12 therefore retain the v8-v10
nonrelevant-selection metric while using their preregistered finite-sample
intervals. Static syntax and version-set inspection passed; no test suite or
retrieval cohort was run, and retrieval quality remains unmeasured.

### Preregistered rubric binding guard (2026-11-23)

Packet construction now checks that the adjudication procedure it is about to
publish has the exact digest declared by the cohort's frozen evaluation
protocol. A packet/protocol mismatch fails closed before reviewers receive the
packet. This catches future gate-version carry-forward mistakes at the
experiment boundary, in addition to the packet and annotation validators'
existing rubric-digest checks. This is a static safeguard only; no retrieval
cohort, reviewer packet, or model run was produced.

### Rootless distinct-experience capacity audit (2026-11-23)

A content-free inventory of persisted rootless experimental history found 470
record files across 41 history directories, with 40 directories containing
records and only 43 unique admitted record IDs/digests. The audit checked the
source files twice for stability, then independently rechecked all 470 file
hashes and record bindings. It is not an atomic snapshot. Of the 43 distinct
records, 15 carry the low-range task family, 7 carry the wide-range family,
and 21 have no objective task-family attribution.

The frozen query-set schema requires unique source-record IDs across queries,
and the rubric prohibits reusing one experience for separate independent
queries. With a minimum of 60 balanced queries, the current rootless corpus is
short by at least 17 distinct experiences; additional records may be needed
if some cannot support an eligible reviewed query. The [capacity audit v2](../../artifacts/experiments/semantic-retrieval-capacity-20261123/corpus_capacity_audit_v2.json)
contains only record identifiers, digests, and file hashes, not prompts or
answers. It supersedes v1, which used an incorrect path depth when counting
history roots. No query cohort, reviewer labels, retrieval scoring, or model
inference was produced; retrieval quality and learning remain unestablished.
`work/verify_semantic_retrieval_corpus_capacity.py --audit <audit.json>` now
recomputes the full source inventory, record-family summary, audit digest, and
shortfall against the query-set schema. Its closed artifact contract is
[`semantic_retrieval_corpus_capacity_audit.schema.json`](semantic_retrieval_corpus_capacity_audit.schema.json).
The check is read-only and fails if the persisted history changes after the
audited double scan.

The v2 audit verifier was rerun against the current inventory on
2026-11-23. Its verifier returned `status: verified`, preserved 470 record
files across 41 directories, and recomputed 43 unique experiences with a
shortfall of 17 against the 60-query minimum. The verified audit digest is
`sha256:d636d17cd1a5c80d9777b5a848f0705c1bea9bdad9152b464a820e6127ff476f`.
No retrieval cohort or inference was performed; this refresh confirms the
corpus-size gate, not relevance, retrieval quality, or learning.

### Expanded explicit rootless-history source set (2026-11-23)

The previous count was scoped to one configured WSL workspace. A new
content-free auditor, [`audit_semantic_retrieval_multi_root_capacity.py`](../../work/audit_semantic_retrieval_multi_root_capacity.py),
supports an explicit set of canonical rootless-experiment history roots and
binds each source file to a hashed root identifier. I selected the
`sentientos-cognition-followup-20261120-wsl`,
`sentientos-cognition-followup-20261121-wsl`, and
`sentientos-cognition-followup-20261122-wsl` roots. The scan double-checked
all three inventories for stability, retained 498 source-file bindings across
56 history directories, and found 71 unique record IDs with 71 distinct record
digests and zero cross-root identity conflicts. Thirty-seven records carry an
objective task-family attribution; 34 do not. This is only a structural upper
bound: the scanner does not verify owner completed-state references, reconciled
writeback receipts, or Phase A eligibility. Therefore the zero raw shortfall
does not establish enough usable sources, and the number of eligible records
remains unknown.

The v3 [multi-root capacity audit](../../artifacts/experiments/semantic-retrieval-capacity-20261123/corpus_capacity_audit_v3.json)
was the initial multi-root count. The corrected v4
[upper-bound audit](../../artifacts/experiments/semantic-retrieval-capacity-20261123/corpus_capacity_audit_v4.json)
explicitly marks owner admission unverified and `phase_a_eligible_record_count`
unknown. Its digest is
`sha256:982ee86fa9e109dcbf72bdebcf905fcaf829dea20c9e7dc7aef637c6b4d07eb1`.
The closed artifact contract is [semantic_retrieval_multi_root_capacity_audit.schema.json](semantic_retrieval_multi_root_capacity_audit.schema.json).
To recheck it in the same WSL checkout, pass the same three roots explicitly:

```powershell
wsl.exe env PYTHONPATH=/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next python3 /mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next/work/audit_semantic_retrieval_multi_root_capacity.py verify --source-root /home/zombinator/.local/state/sentientos-cognition-followup-20261120-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles --source-root /home/zombinator/.local/state/sentientos-cognition-followup-20261121-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles --source-root /home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles --audit /mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next/artifacts/experiments/semantic-retrieval-capacity-20261123/corpus_capacity_audit_v4.json
```

The audit contains IDs, task-family labels, record digests, and file hashes;
root paths are represented by hashes. It does not establish that all 71
records can support eligible independent queries. Query construction,
eligibility review, blinded reviewer labels, retrieval scoring, and model
inference are still outstanding; retrieval quality and learning remain
unestablished.

### Owner-state and receipt lineage audit (2026-11-23)

To sharpen that upper bound, [`audit_semantic_retrieval_owner_lineage.py`](../../work/audit_semantic_retrieval_owner_lineage.py)
uses the runtime history-store validators to check record and receipt digests
and their candidate/admission/operation bindings. It validates each canonical
`composition_state.json` digest and matches completed-tick record and receipt
references. It then calls the official read-only
`inspect_completed_records()` recovery path on each individual record, which
revalidates its admission against the cycle's runtime ledger without repairing
receipts.

Across 56 cycle stores, all 498 record/receipt pairs passed structural lineage
checks and all 477 completed-state references matched. Runtime admission
revalidation passed for 486 records. Twelve records in four stores failed with
`recorded_admission_missing_or_ambiguous`. Among the records that passed all
three checks (stored receipt lineage, completed-state reference, and runtime
admission replay), there are 71 distinct record IDs. The
[owner-lineage audit v6](../../artifacts/experiments/semantic-retrieval-capacity-20261123/owner_lineage_audit_v6.json)
is a read-only inventory, not an atomic cross-root snapshot. The 60-ID minimum
is derived from the query-set schema, SHA-256
`51bf1459d50722ac1eead7ae47e0054a11b0bdfd8e77ae502891dab69d46737b`. It lists the
exact 71 verified record IDs and digests with hashed-root and cycle provenance;
their distribution is 43, 19, and 9 records across the three source roots.
This ID/digest set exactly matches the 71-record multi-root capacity audit.
Thirty-seven records have objective task-family attribution, while 34 do not.

The structural inventory clears the 60-distinct-ID floor by 11, but the
production retrieval freeze and comparison flow are bound to one owner's
history inventory. No one owner currently exposes these three separate stores
as a single comparison corpus. A multi-root owner or equivalent verified
federation path is therefore required before these candidate refs can become a
Phase A freeze. The two positive strata also need 40 distinct source records
consensus-labeled relevant; no reviewer labels or queries have been created.

This strengthens the structural capacity evidence but does not prove Phase A
inclusion eligibility or provide blinded relevance labels. Therefore 71 is
still not a Phase A eligible-source count. Hermes/model inference was not run.

### Multi-root comparison integration contract

Source inspection confirms that the comparison is currently single-store in
three coupled places: `_verified_history_record_refs` derives eligible IDs from
one completed-tick checkpoint, `_prior_projection` resolves each candidate
through one `writeback.store.get`, and the final projection calls that same
writeback controller's `retrieve`. The comparison takes before/after snapshots
from that owner and rejects any inventory change. Consequently, a manifest
containing IDs from several owners cannot be made usable by changing only the
freeze artifact.

A federated comparison implementation must preserve these properties:

1. Revalidate each record against its originating admission ledger and receipt
   with the read-only owner recovery path. Do not merge admission ledgers from
   independent stores: their sequence spaces are local, and replaying one
   merged sequence would change revocation/supersession meaning.
2. Reject cross-root record-ID or digest conflicts and deduplicate exact copies.
   Keep root/cycle provenance alongside the frozen ID/digest list.
3. Define a deterministic global checkpoint order for tie-breaking. A
   timestamp from unrelated owners must not be presented as causal order.
4. Resolve candidate IDs and final projections through the same federated
   read view, and bind the combined record/receipt inventory digest before and
   after each comparison batch.
5. Preserve the existing paired lexical/semantic policy, prompt projection,
   cache-snapshot binding, and no-generative-model posture. Per-root top-k
   results cannot be concatenated as a substitute because that changes the
   candidate ranking and truncation behavior.

[`federated_developmental_history.py`](../../sentientos/federated_developmental_history.py)
now provides that read-only view. It reads only explicitly supplied cycle
roots, verifies each checkpoint and receipt, replays each referenced record
against its originating admission ledger through `inspect_completed_records()`,
rejects identity conflicts, deduplicates exact copies, and exposes a stable
record-ID ordering. It rechecks source checkpoint, ledger, record, and receipt
identities on the before/after inventory calls used by paired comparisons. The
adapter binds a copy of a cognition owner, leaving the template owner intact;
it does not merge ledgers or write to source state.

I bound the view to the existing retrieval comparison method and verified one
CPU-only query over all 71 records. The comparison integrity verifier passed;
the report marked `model_not_configured`, bound the semantic condition to its
explicit lexical fallback policy, and recorded no generative invocation,
learning, or authority. This validates the federation seam only; it says
nothing about semantic-retrieval quality. Query freezing, 60-query collection,
blinded consensus labels, and a configured semantic-encoder run remain ahead.

The corpus is now immutably frozen as
[`federated_corpus_freeze_v1.json`](../../artifacts/experiments/semantic-retrieval-capacity-20261123/federated_corpus_freeze_v1.json)
with ID `devexp-retrieval-freeze-bda164f2a7eb0c44889b016a` and digest
`sha256:bda164f2a7eb0c44889b016a390d3559cade5ffc88278a05cfca9fc3f6c7c831`.
Its [source-binding sidecar](../../artifacts/experiments/semantic-retrieval-capacity-20261123/federated_freeze_source_binding_v1.json)
binds the freeze to the lineage audit SHA-256 and each source checkpoint,
admission-ledger, record-inventory, and receipt-inventory digest. Reloading the
private experiment-store freeze, reconstructing the federated view, recomputing
the corpus manifest and binding digests, and rechecking source stability all
passed. This freeze records no configured semantic embedder, so a new freeze is
required after the semantic embedder is configured; no retrieval-quality
claim follows from freezing the corpus.

### Recorded-experience anchor audit (2026-11-23)

The structural 71-record count was not enough to show that each retained
record names a distinct recorded event. The read-only
[`audit_federated_experience_anchors.py`](../../work/audit_federated_experience_anchors.py)
now verifies the persisted freeze against its source roots and assigns one
typed anchor to each record: a developmental experiment run ID, or an
embodied consequence-chain ID linked to its action-expectation ID.
The closed artifact contract is
[`federated_experience_anchor_audit.schema.json`](federated_experience_anchor_audit.schema.json).

The [latest anchor audit](../../artifacts/experiments/semantic-retrieval-capacity-20261123/federated_experience_anchor_audit_v4.json)
contains 71 anchored records: 37 experiment-run anchors and 34 embodied
consequence-event anchors. It found no duplicate anchor groups or unanchored
records, so the structural 60-event floor has no shortfall. The audit is
reproducibly verifiable against the frozen corpus and current source inventory.
The latest audit digest is
`sha256:96680f405dd2b239fc50b0665c6609eb665e30440a34b29d33f33180bf1a5aaa`.
Compared with v1, v2 also checks that each embodied chain's digest-bound
component-source list includes its linked action-expectation record and that
the chain payload ID agrees with its subject ID. Rebuilding the stricter audit
produced the same 71 anchors, confirming those links in the current frozen
records. The audit CLI accepts repeated `--cycle-parent` arguments and expands
only direct child directories containing both resident-cognition history and
state. Replaying the v2 report from the three parent roots verified its digest
and source inventory, avoiding a manually enumerated 49-cycle command line.
The CLI can also persist that verification result as a separate read-only
receipt, specified by
[`federated_experience_anchor_verification.schema.json`](federated_experience_anchor_verification.schema.json).

The v4 artifact additionally binds the exact source-snapshot inventory exposed
by the reconstructed view: 47 snapshots with digest
`sha256:98ff65b8574ac0cd8a5de8758cb7a93fc988a1f29e6111d731f96f3de2a277a3`.
The v4 artifact and receipt also use schema v3, correctly versioning the new
snapshot-binding fields. Its separate [v4 replay receipt](../../artifacts/experiments/semantic-retrieval-capacity-20261123/federated_experience_anchor_verification_v4.json)
reproduces the audit digest and snapshot binding. Retrieval scoring now requires
both the source replay and matching snapshot count/digest, and emits these
bindings in score schema v3. This inventory digest binds the recorded snapshot
list; it does not make the multi-root read atomic or establish that the listed
events are statistically independent.
The earlier `*_v3.json` files remain immutable history, but their new fields
were emitted under the old v2 schema label; use the v4 audit and receipt for
validation and any subsequent scoring.

These anchors identify distinct recorded events, not independently sampled or
independently adjudicated experiences. The corpus remains concentrated in
three task families (37 developmental intervention runs and 34 synthetic
avatar consequence events). Thus this audit does not establish statistical
independence, Phase A eligibility, relevance labels, semantic retrieval
quality, or learning. No queries or reviewer labels have been created, and the
frozen corpus has no configured semantic embedder. Model inference was not
performed.

### Archive-derived source manifest (2026-11-24)

The live-owner `freeze-sources` command requires private cognition and serving
configuration paths. Those configurations are unavailable for the archived
rootless cycles, so a separate CPU-only freezer now binds the already verified
archive directly. It replays the v4 experience-anchor audit, reconstructs the
admission-verified read view, checks all 47 source snapshots, and partitions
each record by its verified source-root identity. The opaque source IDs and
per-source inventory digests are sealed in
[`federated_archive_source_manifest_v1.json`](../../artifacts/experiments/semantic-retrieval-capacity-20261123/federated_archive_source_manifest_v1.json);
the companion [binding artifact](../../artifacts/experiments/semantic-retrieval-capacity-20261123/federated_archive_source_binding_v1.json)
ties those IDs to the source-root hashes, snapshot inventories, audit digest,
and source-replay receipt digest.

The manifest contains three sources with 19, 43, and 9 records, for 71
source-qualified records total. Both artifacts validate against their schemas.
The source manifest can support query-set construction without live owner
configs. A new archive-backed resolver also supports the
`archive-review-packet` command: it reopens the same audited cycle roots, checks
source-root-to-record membership, and emits the same blinded reviewer packet
contract as the live-owner path. The standard comparison `run` and
`review-packet` commands still re-resolve records through live owners; the
archive-specific commands support the frozen rootless sources.

The new `archive-run` command closes that runner gap for a frozen archive. It
loads the saved source-replay receipt and anchor audit, then rechecks the
receipt digests, all source-root memberships, record digests, and the full
source-snapshot inventory against the supplied archive roots before invoking
the ordinary-chat lexical and semantic selectors. It requires a
sentence-transformers model ID and immutable revision; the embedding
implementation loads only from local cache and pins both model loading and
encoding to CPU. It does not invoke a generative model, alter the history
archive, or establish learning. The command accepts either exact cycle roots
or parents containing them. Its source roots must be the archived roots
represented in the frozen binding; the original private experiment store is
not recreated by this route.

A first query cohort is now frozen in
[`federated_semantic_history_query_set_v1.json`](../../artifacts/experiments/semantic-retrieval-capacity-20261123/federated_semantic_history_query_set_v1.json):
60 unique questions, balanced across 20 paraphrased-experience, 20
lexical-distractor, and 20 no-applicable-history queries. Its ID is
`federated-queryset-7d204b6253b8a1e3cd6e97df` and digest is
`sha256:7d204b6253b8a1e3cd6e97df54834d388136174ae6fe9b7e2706a3c9e290b3c1`.
The 60 source references bind to 60 distinct event anchors in the verified
archive. For no-applicable-history questions, the anchor is only a sampling
unit; it does not assert that the referenced record answers the question. The
query set has no target-model identity and was frozen without inference.

The source manifest and query set validate against their schemas and runtime
binding checks. No reviewer labels exist yet. The semantic embedder remains
unconfigured in the frozen corpus. A locally cached CPU embedder is available
at revision `c9745ed1d9f207416be6d2e6f8de32d1f16199bf`; `archive-run` accepts it
without occupying the GPU. The original private experiment store is absent,
but the WSL archive roots represented by the binding were found and replayed
against their saved source-replay receipt.

### CPU retrieval comparison and budget follow-up (2026-11-23)

The archive read view reconstructed 71 records from three source roots across
the 2026-11-20, 2026-11-21, and 2026-11-22 WSL state stores. Its 47-snapshot
digest exactly matches the frozen source binding. All 60 query anchors resolve
to source-qualified records and distinct event anchors. No private store was
recreated. The archive resolver verified record membership and source snapshots
before each comparison.

The first frozen query set used an 8,000-character context budget. The
CPU-only MiniLM comparison validated at digest
`sha256:e959b72d843b9f9f464170b4ad96a95e1ab441075229e5a03c9ed43315a0d576`,
but both selectors returned empty selections for all 60 queries. A targeted
paraphrase diagnostic found that its anchored record scored 0.440 cosine
similarity and 44 of 71 candidate records exceeded the existing 0.25 semantic
threshold. The one-record federated context still measured 8,529 characters,
above the frozen budget. This outcome demonstrates a prompt-budget rejection;
it does not measure relevance or retrieval quality.

The v1 comparison and query set remain unchanged. An explicitly exploratory
follow-up reuses the same 60 questions, strata, and source-event anchors with a
16,000-character context budget. The query set is
[`federated_semantic_history_query_set_v2.json`](../../artifacts/experiments/semantic-retrieval-capacity-20261123/federated_semantic_history_query_set_v2.json),
ID `federated-queryset-7d2849adb59428b019ac01c2`, digest
`sha256:7d2849adb59428b019ac01c2de663d33134902de9304e9d27b94a823d984357f`.
Its comparison is
[`federated_semantic_history_comparison_cpu_minilm_budget16k_exploratory_v1.json`](../../artifacts/experiments/semantic-retrieval-capacity-20261123/federated_semantic_history_comparison_cpu_minilm_budget16k_exploratory_v1.json),
digest `sha256:5dce1e8467397de3ffa5506448927bfce3ada04bd2629bd2c5d7bece0c4400c9`.
Both artifacts validate against the frozen manifest and query set. Both
selectors returned nonempty results for every query with zero semantic
fallbacks. Their selected sets were identical for 8/20 paraphrased-experience,
6/20 lexical-distractor, and 20/20 no-applicable-history questions. These are
descriptive selector-behavior counts only; no independent relevance labels,
retrieval gate score, or learning evidence exists.

The CPU runtime was isolated from the project environment and ran offline with
CUDA disabled: Python 3.12.3, Sentence Transformers 5.7.0, Transformers 5.24.0,
and PyTorch 2.11.0+cpu, limited to two CPU threads. The model identity digest
was `sha256:bee56ccdccb76b59049b50af5299c959816a7305a88ac55b9be1db2bf60d157e`.
No Hermes or generative-model inference occurred. The embedder ran only for
semantic retrieval; neither comparison establishes model attention, durable
learning, or improved reasoning.

After the exploratory run, `semantic_embeddings.py` was updated to prefer
Sentence Transformers' `get_embedding_dimension()` and fall back to the older
getter when needed. This removes the 5.7.0 deprecation warning while preserving
compatibility. The comparison remains bound to its recorded retrieval
implementation digest
`sha256:cc9a578d9f7d275a376ebcab2c1808a60c077ee3d46e74fa75b90738dc6a64b2`;
the current implementation digest is
`sha256:9eeb6ee557b87a0e659de92e33f34b37891dfb2a5082826d3ae83dbf87a0eafa`.
The updated getter has static compilation evidence; it has not been used in a
new semantic comparison yet.
This work also corrected the federated manifest builder's digest encoding:
nested corpus digests are now `sha256:` prefixed as required by the schema,
and source revalidation compares them against the canonical corpus digest.

### Frozen archive replay after append-only growth (2026-11-25)

A CPU-only attempt to rerun the exploratory 16,000-character comparison from
its frozen v2 query set stopped at `federated_archive_binding_invalid`, before
retrieval or embedding. The source binding and anchor audit still validate
against their own recorded digests and agree on the original 47-snapshot
inventory. The three live WSL archive parents now expand to 139 cycle roots and
130 source snapshots, so they no longer match that frozen inventory. Filtering
the current view to cycles containing the frozen 71 candidate record IDs still
produces 129 snapshots and 21 additional record IDs; the original 47-snapshot
view cannot be reconstructed from the current roots using those record refs.

The old v2 query set and comparison inputs remain unchanged. No replacement
comparison or relevance result was produced by this failed attempt. The
subsequent replay and its limits are recorded below. Relaxing the old global
snapshot check alone would make the historical artifact's source snapshot
unverifiable; replay can proceed only after recovering the exact frozen rows.

### Versioned snapshot-scoped archive binding

The archive binding writer and reader now support v2. A v2 binding stores the
complete frozen snapshot rows, including each cycle ID and its composition,
admission-ledger, record-inventory, and receipt-inventory digests. Replay
requires every bound row to still exist unchanged under the same source-root
identity, then builds each source's history-state digest from that frozen row
set. Later appended cycles are excluded from the replay view; removed or
changed frozen cycles still reject. The v1 reader keeps its previous exact
whole-view snapshot requirement because its binding contains only aggregate
digests and cannot identify the original rows.

The versioned contract is
[`federated_archive_source_binding_v2.schema.json`](federated_archive_source_binding_v2.schema.json).
The old binding was converted using the snapshot rows in the separately
digest-bound corpus-freeze source binding. The conversion rechecked the v1
binding, source manifest, anchor audit, anchor verification, and per-source
snapshot digests, then produced
[`federated_archive_source_binding_v2.json`](../../artifacts/experiments/semantic-retrieval-capacity-20261123/federated_archive_source_binding_v2.json)
with digest
`sha256:7e5a786e1bf35d0a1f50896f6a258e0873b4290db4cbc57e7899e7fbbf156e21`.
The archive runner reloaded those 47 exact snapshot rows from the expanded
roots and validated the comparison against all 60 frozen queries.

### Snapshot-scoped replay result and CPU encoder availability (2026-11-25)

The replay produced
[`federated_semantic_history_comparison_cpu_minilm_budget16k_exploratory_v2.json`](../../artifacts/experiments/semantic-retrieval-capacity-20261123/federated_semantic_history_comparison_cpu_minilm_budget16k_exploratory_v2.json),
digest
`sha256:b57262c911215fe92c8f86c32ff63d57f7ab1848a3080b764f896b35422940cb`.
Its comparison digest validates against the frozen manifest and query set.
All 60 queries are marked `semantic_fallback_to_lexical`, 20 in each stratum;
the semantic and lexical selections are consequently identical for every
query. This attempt used a mistyped, uncached revision and WSL's empty default
cache path. The comparison's embedder identity digest records the requested
identity, not proof that the encoder loaded. This artifact provides no semantic
retrieval measurement, relevance result, learning evidence, or model-attention
evidence. The exact cached revision was subsequently found in the Windows
Hugging Face cache and loaded by pointing WSL at that cache explicitly.

The corrected CPU-only replay is
[`federated_semantic_history_comparison_cpu_minilm_budget16k_exploratory_v3.json`](../../artifacts/experiments/semantic-retrieval-capacity-20261123/federated_semantic_history_comparison_cpu_minilm_budget16k_exploratory_v3.json),
digest
`sha256:0e4d688c94c1f69e6dfeceba16c9652334b9a9480bcdc5c8bef30b86ddb4ddea`.
It uses the locally cached immutable revision
`c9745ed1d9f207416be6d2e6f8de32d1f16199bf`; the CPU encoder loaded and returned
384-dimensional vectors. All 60 queries completed without semantic fallback.
Counting the source-qualified records in each selection, the two selectors
differed on 12/20 paraphrased-experience queries and 14/20 lexical-distractor
queries. The earlier report transposed the agreement and disagreement counts.
On all 20 no-applicable-history queries both selectors returned the same
nonempty list in the same order. Counting any change in the ordered list,
including a change in membership, gives 16/20 and 17/20 for the first two
strata respectively. These counts describe selector behavior;
without independent relevance labels they do not establish that semantic
retrieval is better or worse. No gate score, model attention, durable learning,
or reasoning improvement is established. CUDA was hidden, the embedder ran on
CPU, and no generative model was invoked. WSL used
`HF_HOME=/mnt/c/Users/aprmu/.cache/huggingface` with both Hugging Face offline
flags enabled, so the pinned model was loaded from the existing local cache
without network access.
