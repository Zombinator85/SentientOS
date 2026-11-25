# Preregistered resource strategy comparison

## Purpose

The existing `resource_quality_then_measured_call_units:v1` recommendation
compares the three history exposure conditions in a developmental-history
intervention. It does not compare task strategies. Current history conditions
also perform one inference each, and the resource ledger measures one call unit
per completed inference. Those results cannot demonstrate that the system
learned to allocate calls more efficiently.

This protocol defines the next experiment needed for that claim. It compares
explicit task-strategy alternatives on one frozen held-out task suite while
preserving the exact model setup and measuring the complete invocation cost of
each alternative. A strategy may make one or more inference calls; each call
must have a distinct invocation receipt and its own reconciled resource-attempt
chain. A history-condition label cannot stand in for a strategy identifier.

Protocol creation and reload enforce a closed invocation-budget shape:
`max_input_chars` is at most 8,000, `max_output_chars` at most 4,000,
`max_new_tokens` at most 512, `timeout_seconds` at most 120, and
`max_calls_per_correlation` is exactly one. Each strategy call has its own
unique correlation ID across the full campaign and still must fit the separately
frozen per-strategy and campaign invocation limits. Restart reconstruction
rejects correlation reuse within or across trials. These are experiment-level
ceilings; the serving authority may impose stricter limits. A digest-valid
protocol outside these bounds is
invalid and cannot be preregistered or reconstructed.

## Preregistration

Before any comparison inference, call
`persist_resource_strategy_comparison_protocol`. It writes a separate
write-once preregistration record; campaign publication fails unless that
record already exists and contains the exact protocol. The record's local
wall-clock timestamp is checked against invocation receipt timestamps, but
neither timestamp has independent time authority. The protocol contains:

- a unique comparison ID and protocol digest;
- the exact held-out task descriptor digest, probe count, ordered probe inputs,
  and independent evaluator identity;
- the minimum full-suite correctness requirement;
- the exact serving-model identity digest, model ID, authority-map digest,
  invocation-budget digest, and generation-configuration digest shared by every
  strategy;
- two to eight ordered, named strategy alternatives, each bound to a digest of
  its strategy descriptor and prompt-construction policy. Each descriptor
  freezes minimum and maximum invocation counts and declares that the scored
  answer is the final invocation's output for each trial;
- a trial count that is a multiple of the number of strategies, with a
  deterministic rotating order so each strategy occupies each position equally
  often. Every trial digest binds the comparison, exact task, and ordered
  strategies. The protocol also caps maximum total campaign invocations to keep
  persisted evidence within its storage bound;
- the aggregation rule and explicit non-claims.

Strategy alternatives describe different task procedures, such as a single
generation or a generation followed by an independent verification call. The
protocol fixes each procedure before results are observed. It does not infer a
strategy from a history treatment, a model's retrospective explanation, or a
condition name.

## Trial evidence

Each trial/strategy outcome binds, in the exact preregistered schedule order:

1. the exact strategy ID and descriptor digest, trial index and digest, task
   digest, model identity, and generation configuration from the protocol;
2. the verifier-recomputed held-out score and score digest;
3. the ordered invocation receipt IDs and digests for every call the strategy
   made, with one unique request correlation ID per call across the campaign;
4. one unique resource attempt for each invocation, retaining its
   `attempt_begun`, `measured_*`, and `reconciled` receipts and predecessor
   digests;
5. the exact invocation receipt digest in each reconciled receipt's effect
   binding.

Admission requires a one-to-one join: no invocation may be missing a resource
chain, no resource chain may be attached to multiple invocations, and no extra
or duplicate receipt may be counted. The measured and reconciled values must
match within each attempt. Total cost is the sum of the terminal reconciled
`call_units_consumed` values across that strategy's calls. Incomplete attempts,
unknown measurements, identity drift, task drift, score mismatch, and ambiguous
joins make that strategy/trial incomparable; missing cost is never inferred.
Score rows must cover the protocol's exact ordered probe inputs, and their
answer and aggregate counts must agree. New v5 campaign outcomes also carry the
private frozen objective task plan and a deterministic scorer receipt. The
scorer reconstructs the task from its nonce-bound plan, checks that its public
descriptor matches the preregistered task, binds the exact retained invocation
output text to its receipt digest, then independently parses and scores the
family suite against the frozen integer-affine oracle. The receipt binds
the comparison protocol digest, task-plan digest, final invocation receipt ID
and digest, output digest, scorer identity, score digest, and exact ordered
probe coverage. The private plan is campaign evidence and must never be added
to a model prompt. The receipt is unkeyed evidence, not a digital signature;
restart reconstruction reruns the scorer from the same private plan and exact
output bytes. The campaign producer must retain the bounded output by calling
`LocalModelInvocationReceipt.to_dict(include_output=True)`; the default receipt
projection omits it and cannot produce an attested score.

## Selection and claims

The evaluator first excludes alternatives that fail the preregistered
full-suite correctness requirement on any trial. Among eligible alternatives,
it ranks by total verifier-recomputed correct probes across all trials, then
by total reconciled call units across all trials. It returns no recommendation
for an unresolved tie or incomplete comparison.
Historical recommendation output has no authority over the current task and
does not prescribe what the system should desire or become.

A lower measured cost is demonstrated only when correctness-equivalent
alternatives have different, complete, owner-reconciled call totals. A selected
alternative is not evidence of learning by itself. To claim durable strategy
learning, a later preregistered held-out episode must show that retained,
digest-verified experience changes the strategy selected or executed and that
the new outcome is independently scored. Model-replacement transfer remains a
separate experimental question.

The protocol does not infer CPU, GPU, energy, latency quality, truth, causal
benefit, general intelligence, agency, or consciousness from call units or
recommendations. Synthetic fixtures may verify evaluator ordering but are not
production evidence.

## Implementation boundary

The existing pipeline does not yet create these artifacts. Its condition
outcomes contain one inference receipt per history condition, and its resource
recommendation is intentionally typed as a historical condition comparison.
The first isolated implementation is in
`sentientos.resource_strategy_comparison`: it builds the frozen protocol and
structurally validates supplied invocation chains, then requires a
`resource_owner_projection` for each trial/strategy outcome. The owner creates this
read-only exact-scope projection from its ledger snapshot, retaining every
receipt for the selected attempts while binding the full ledger digest. The
owner also exports one bounded full-ledger image with
`resource_strategy_owner_ledger_snapshot`; every trial projection must name
that same snapshot digest. The evaluator reopens this image through the
resource ledger's read-only validator, reconstructs its digest and invariants,
and checks each projected allocation, attempt, and receipt list against it.
The snapshot is stored once in the campaign bundle rather than copied into
every trial outcome. The
evaluator verifies the projection record digest, exact invocation scope,
owner disposition, receipt chains, and correspondence to invocation receipts
before reporting `verified_from_reconstructed_owner_ledger_snapshot`.
`persist_resource_strategy_comparison_campaign` writes
the exact protocol, outcomes, one bounded full-ledger image, and deterministic
report as a write-once JSON bundle. `load_resource_strategy_comparison_campaign` checks
the artifact and protocol digests, reconstructs the owner ledger from its full
image, reruns the evaluator from saved outcomes, and rejects report or encoding
mismatches. This provides restart reconstruction of the report and ledger
invariants from bundled evidence. Publication is write-once at the API
boundary, but the bundle and ledger digests are unkeyed: an actor able to
rewrite the files can recompute them. They are not signatures or adversarial
custody proofs.
New campaign persistence and direct evaluator calls require the v5 scorer gate
by default; only the restart loader's explicit v4 compatibility path preserves
the historical unattested scoring posture.
The separate preregistration record must already exist and must exactly match
the campaign protocol. Each invocation receipt's timezone-aware event time is
required to be no earlier than that record's timestamp. Since both values are
local wall-clock claims, this is sequencing evidence inside the configured
process, not an independently trusted timestamp or proof against a post-hoc
operator rewrite.
The evaluator requires every preregistered trial/strategy outcome in schedule
order and aggregates only after every trial passes validation. It does not
estimate statistical significance or confidence intervals. New v5 campaign
bundles independently reconstruct each score from the frozen private objective
plan and exact final invocation output; `build_resource_strategy_trial_outcome`
checks the scheduled call receipts against the preregistration time and
constructs this score-and-receipt pair from completed evidence, and restart
loading recomputes the attestation before accepting the report. No inference
runner currently calls this helper. Legacy v4 bundles retain their original report
reconstruction semantics, but their self-digested scores are not eligible for
resident cognition projections. The comparison APIs do not invoke models or
write developmental-history facts. The resident cognition owner can expose a
configured, exact-model campaign only when its score posture is
`private_plan_score_recomputed_and_final_invocation_bound`, with task-family
reuse explicitly marked as unverified transfer, and retain that projection in
invocation evidence.
This does not create a developmental-history fact or establish learning. The new purpose identifier
must also receive its own explicit
non-production invocation-authority review before any runner may use it. The
purpose currently has no entry in the local model authority-purpose tuples, so
the campaign runner remains unauthorized by the configured authority maps.
Existing history-condition records must never be reinterpreted as strategy
outcomes.

The acceptance artifact now makes that review concrete without performing it.
The review record must identify the exact authority-map diff and digest, bound
per-trial and campaign call counts plus generation tokens, request linkage to
the preregistered strategy schedule, disabled tool/memory/host/repository/action
capabilities, scorer-data exclusion from prompts, and resource reconciliation
for denied or incomplete calls. It must also identify the reviewer, source
revision, decision, conditions, and a digest-bound record. Until a reviewer has
recorded a decision and the authority maps have been explicitly updated, the
purpose stays unregistered and no runner may invoke a model. This checklist is
review preparation, not authorization evidence.

`resource_strategy_comparison_prompt_projection` is used by resident cognition
only during an explicit preregistered objective plan when config v5 explicitly
names a campaign root and up to eight campaign IDs. Ordinary chat and other
non-objective cognition calls do not open campaign artifacts. The owner reopens
and reconstructs only those campaigns. A projection reaches an
objective prompt only when task family and observed model identity match exactly.
Campaigns with the same task digest as the current objective are withheld from
the prompt to keep their scored source suite out of a held-out evaluation.
Different-digest campaigns are also withheld if any probe input overlaps.
Invocation evidence retains the withheld campaign artifact digests, task-digest
relation, probe counts, and overlap count. A different digest with disjoint
probes in the same family has
`prompt_eligibility=eligible_same_family_disjoint_probe_transfer_unverified`;
the source descriptor carries `withheld_source_task_or_probe_overlap` otherwise,
and the owner does not pass it to the objective prompt. Different-digest evidence cannot establish
current-task performance. The task-family label is operator-declared, protocol-bound metadata,
not proof that two task suites are equivalent. Invalid or unprojectable campaigns do not provide strategy
guidance. It carries the frozen strategy descriptor (verified against its
protocol digest) along with aggregate scored outcome and reconciled call cost,
so later cognition can inspect what the compared procedure actually specified.
The descriptor is presented as historical data, not executable instruction or
authority. It retains `selection_reason` and the evaluator's
`correctness_equivalent_receipt_chain_cost_variation_observed` flag, so a quality
winner is not misrepresented as a cost-selected strategy and call units are not
treated as host compute. The prompt projection and its digest-bound source identifiers are
retained in upstream invocation evidence. Multiple eligible configured
projections are considered in configuration order under an 8 KiB maximum that
shrinks to fit the configured cognition input bound and a reserve
for developmental history. Omitted or invalid IDs are marked unavailable, not
scored as failures. The effective byte budget is retained in invocation evidence.
No directory scan or implicit campaign selection occurs. This
provides one evidence path from a comparison bundle to a
later task prompt, but it still does not demonstrate that a later answer changed
because of that evidence, improved, or generalized. A held-out strategy episode
with independently validated scoring remains necessary to measure that effect.

The upstream `campaign_retrieval_audit` records one outcome per configured ID
when history is enabled: unavailable or invalid artifact, no projectable
recommendation, task-family or model-identity scope withholding, probe-integrity
withholding, prompt-budget exclusion, or actual prompt inclusion. Artifact
digests accompany reconstructed scope decisions. This audit is not exposed to
the model and does not claim that an included projection was attended to or
causally used; it makes the intended exposure condition reconstructible for
later analysis. When the experiment withholds history, evidence records that
condition without opening the configured campaign artifacts.
Campaign retrieval status, unavailable IDs, and budget diagnostics are retained
only in upstream evidence. The model sees an eligible projection when one fits;
retrieval failures and diagnostic counts do not become a second prompt treatment.
The same upstream context binds the exact prompt digest used by the governed
invocation request, and the owner checks that the request's prompt digest agrees
before inference. This joins the retrieval audit and selected projections to
the actual prompt commitment without retaining raw prompt text in the receipt.
Before building the request, the owner also confirms that every selected
projection's canonical JSON appears in the exact rendered prompt and that the
bound context has the same projection list as upstream evidence.
During restart reconstruction, resident cognition revalidates the v5 audit
against the persisted request: configured-ID order, inclusion statuses,
projection digests, overlap-withheld rows, and request prompt digest must agree.
The exposure posture must also match the request linkage's condition ID and
`history_present` flag. Experimental `history_withheld` arms are distinguished
from unrelated calls whose history is absent, such as a scoped `prior-context`
probe; both carry no campaign retrieval audit or projection.
Older v3/v4 contexts remain readable under their historical checks; unknown
future context versions fail closed until an explicit validator is added.

## Next empirical gate: strategy use on a held-out task

The next learning claim requires a separate preregistered experiment. Its held-out
task must have a different private task digest and non-overlapping probe inputs
from every source campaign. The exact model identity, generation configuration,
task-family label, strategy executor mapping, quality threshold, invocation budget,
trial schedule, and scorer must be frozen before inference. The family label
remains an operator declaration; matching it only admits a tentative source
projection and is not proof of task equivalence.

Use counterbalanced paired conditions that differ only in whether the validated
campaign projection is supplied to cognition. Record the strategy actually
selected and the executor's invocation sequence; a retrospective explanation
alone does not establish strategy use. Score each held-out output through an
independent scorer path and bind it to the final invocation output. Reconcile
every call to the resource owner's attempt and receipt chain. Compare strategy
selection frequency, held-out quality, and call units separately. Repeated
improvement requires replication over additional preregistered held-out task
digests; report negative, mixed, and incomparable outcomes. The campaign
projection's source-suite score must not be reused as the held-out outcome.

This design would establish at most a bounded, same-model, same-declared-family
effect for the tested strategy and held-out tasks. Model-replacement transfer,
causal generalization beyond that family, autonomous authority, and general
developmental learning remain separate claims. The runner and independent scorer
receipt path are not implemented yet, and the current score posture is not
sufficient for this gate.
