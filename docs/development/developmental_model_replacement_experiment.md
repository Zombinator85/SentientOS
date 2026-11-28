# Developmental cognitive-model replacement experiment

This explicitly invoked instrument asks what digest-level observations change when one frozen current World-State projection and one frozen developmental history projection are presented to two distinct, already-governed local cognitive endpoints. It is not a production hot-swap and performs no model activation, serving transition, adoption, download, history write, or canonical explicit-user-retention write.

## Frozen causal context and operational identity

Context v1 binds the exact snapshot and current-projection IDs/digests, fact IDs, projected fact/source/conflict content digest, developmental record IDs/digests and record-set digest, instruction/template digest, inference budget, temperature-zero generation posture, schema, and optional repository generation identity. Context v2 keeps those frozen content fields and changes how its compact binding manifest is content-addressed. Context v3 adds digest-only bindings from each selected current fact ID to the canonical digest of its exact projected row. The semantic prompt is constructed from that object once: matching A/B conditions are byte-equivalent except that withheld conditions contain no history projection. Neither model labels nor lineage evidence enter the prompt.

At context creation and in-memory verification, the selected current fact-ID
set is bound to fact rows inside the frozen current-projection payload. V1 and
v2 compact manifests omit that payload, so reload cannot independently rederive
the row-to-ID match. V3 stores an ordered pair of each selected fact ID and the
SHA-256 digest of its canonical row. Reload requires each pair to have exactly
the `fact_id` and `fact_digest` keys, checks pair order, uniqueness via the
bound fact-ID list, digest shape, and the content-addressed context identity.
The raw fact rows remain omitted. These digests preserve the sealed mapping;
they do not authenticate the source projection or prove that an external source
served those rows.

## CPU-only v3 context artifact exercise

The v3 reload contract has now been exercised with a minimal persisted context
containing two current fact rows and one history row. A valid round-trip
preserved the ordered `current_fact_bindings`, and the compact manifest
contained neither raw current-projection nor history-projection payload.

The tamper exercise changed one fact-row digest, recomputed the canonical outer
manifest digest, and reloaded with the original context ID and digest pinned by
the protocol. Reload failed with `context_manifest_identity_mismatch`. Omitted,
reordered, duplicated, and extra fact-binding rows each failed with
`context_fact_binding_invalid`. After each mutation, restoring the original
artifact allowed a verified reload. These outcomes establish the v3 sealed
manifest integrity behavior exercised here; they do not authenticate the
external source projection or show that any model used the mapped facts.

The corrected private report is
[context-v3-artifact-exercise-canonical-write.json](../../../sentientos-data/rootless-experimental/model-replacement-v3-context-verification-20261128/context-v3-artifact-exercise-canonical-write.json)
(mode 0600, SHA-256
`76d9e8787c17bcd4f8829ebb06169c26793fb86e69ded6be09d1f0faf5518df0`). It
binds source commit `e072c94030e24e9cc1bd541d69f7f68617dacd75` and
implementation SHA-256
`e7ca1f7e8af914a3146649d427ffe3a95214a42101829b8f5619800811aeb44f`; it
records `inference_performed=false`, `model_loaded=false`, and
`gpu_accessed=false`.

The first harness attempt serialized the mutated artifact as indented JSON,
which violated the store's canonical-byte requirement and was rejected early
with `context_artifact_invalid`. That result did not exercise the v3 binding
checks and is retained separately as
[context-v3-artifact-exercise.json](../../../sentientos-data/rootless-experimental/model-replacement-v3-context-verification-20261128/context-v3-artifact-exercise.json)
(mode 0600, SHA-256
`a23ac0e2945dffde7ef20b77cdf10fa362a4eab6415a1f4b9c2e596d97ae8ae1`). The
corrected harness rewrote tampered manifests using the store's canonical JSON
encoding. The exercise was model-free and required no GPU. It establishes
reload integrity for these generated artifacts only; it does not establish
cross-model semantic continuity, learning, or authority.

Context binding v2 addresses a separate reload-integrity gap: its context ID is
derived from the compact persisted manifest fields, including the original
full-context digest. The preregistered protocol pins that ID, so changing
manifest references and merely recomputing the manifest digest is rejected on
reload. V1 contexts retain their original digest-derived IDs and verification
behavior. V2 still cannot independently rederive the source payload's
row-to-reference relation after that payload has been omitted. V3 binds the
current fact-ID-to-row-digest pairs to protocol identity without retaining raw
current or historical content.
New World-State projections label record-set continuity as bound only for v2 and v3
context manifests. Runs using v1 manifests remain historically readable, but
their history continuity is projected as unavailable rather than promoting
the weaker manifest binding. Existing persisted projection shapes are not
rewritten.

Context verification now requires unique bounded history record IDs and
well-formed `sha256:<64 lowercase hex>` record digests before validating the
record-set digest. Before sealing, verification binds each projected history
payload row's `record_id` and `record_digest` to the corresponding reference.
The compact persisted manifest omits raw history payload; reload validates the
manifest and digest-only references, not that row-to-reference relation. Any included `authority`, `current_truth`, policy, goal, or
retention/effect-authority marker must remain false, and historical posture
markers must retain their non-current-truth meaning. A digest-shaped prefix
alone is not accepted as record identity evidence, and a payload whose rows
disagree with the selected references or claim authority cannot enter the A/B
prompts.

When a caller already has an exact task/source selection, `FrozenCausalContext.create_from_admitted_history(writeback=..., history_record_ids=...)` rechecks the writeback owner's completed records and receipts, then freezes their IDs, digests, and bounded record content for both endpoints. Task-family score lineage remains inside its admitted source fact. This factory does not decide task relevance or create a history admission.

For non-synthetic resident transition ingress, the predecessor and successor references must resolve to the same frozen context. Its selected history IDs and digests are checked against the matching records in the transition protocol's complete initial resident history boundary. The binding retains the selected IDs/digests and the complete boundary digest/count, so an experimental subset stays distinct from the resident's full history. Missing records, repeated resident record identities, digest substitution, or different A/B contexts fail closed before ingress. This verifies frozen evidence correspondence; it does not observe the daemon's running source generation or authorize history access.


The live A→B→A controller now re-resolves the complete resident boundary only
after cognition has drained and the gate is held for its first A quiescence. It
requires exact equality with the protocol's frozen initial boundary. A mismatch
reopens the cognition gate and records a failed stage before any model activation
is attempted. Journal recovery recomputes the quiescence token digest and checks
that its recorded first-A observation contains the frozen boundary, so the
original process's check remains auditable after restart. This catches
intervening history, activation, or serving-session changes after
preregistration; it does not authenticate the boundary's external custody.
Before each B or restored-A activation, while cognition remains quiesced, the
controller compares the current full boundary with the latest quiescence
observation and binds the matching boundary digest into activation-stage
journal evidence. Recovery checks that digest against the preceding quiescence
token. This makes retained-state continuity across the activation boundary
explicitly auditable; it does not prove model-internal use or semantic continuity.
The boundary builder now rejects supplied record/receipt lists unless they are
equal in length, have unique identities, and each receipt names the matching
record ID and digest. Production boundaries obtain these pairs from the
writeback owner's verified completed-record inspection; synthesized receipts
are confined to the helper's omitted-receipt fixture path.

Each `CognitiveModelIdentity` binds model ID, semantic artifact identity, content SHA-256, known size and sidecar digest, configuration digest, engine/runtime family, candidate index, production/fallback posture, exact authority-record custody, and the exact active-model identity structure. A and B must differ in semantic artifact/content/configuration identity. Identity is not inferred from a display name. Model identity is neither system identity, runtime identity, nor configuration identity.

## Provenance is evidence, not authority

`sentientos.model_development_provenance:v1` is stored separately from the operational authority map. Claims bind their exact subject model identity, relation, optional parent/teacher label, evidence source and digest, and one of `locally_observed_identity`, `source_bound_reported_claim`, `operator_attested_claim`, `cryptographically_bound_attestation`, or `unknown`. An absent manifest becomes `unknown`; names never imply teacher, distillation, synthetic-data, successor, or AI-assisted lineage. These postures preserve source custody but do not make a claim current truth, grant admission or authority, or establish an experimental conclusion.

## Preregistered conditions and measurements

Before inference, `sentientos.developmental_model_replacement_protocol:v1`, both provenance manifests, and the fixed order are atomically persisted under `developmental_experiments/model_replacement/{protocols,provenance,runs}`:

1. `model_a_history_present`
2. `model_a_history_withheld`
3. `model_b_history_present`
4. `model_b_history_withheld`
5. `model_a_history_restored`

The sequence is fixed and keeps restoration last; within-run condition order is
not counterbalanced. The artifact can establish which outputs differed under
this schedule, but it does not isolate order or carryover effects. Reported
history/model contrasts therefore remain digest-level associations.

The instrument compares A+H/A-H, B+H/B-H, A+H/B+H, A-H/B-H, and baseline A+H/restored A+H. Durable observations contain prompt/output/request/receipt digests and identities, never raw output. Before and after every call it checks the exact endpoint identity, frozen context, and immutable protocol; it also checks completed non-fallback inference and actual temperature zero. For persisted-context runs, reload additionally requires every observation's current-projection ID/digest and history record IDs/digests to match the exact context artifact, with empty history references in withheld arms. For objective tasks, the observed `max_new_tokens` must match the preregistered budget both during execution and when stored observations are reverified after restart. Changed model/artifact/configuration/authority identity, causal context, history, protocol, generation posture, or an inexact final A restoration fails closed.

Classifications are limited to no observable history effect, A-only, B-only, both-model history association, restoration instability, or contamination. Digest equality/inequality is not semantic scoring. Even a stable both-model association does not prove learning, model-independent identity, persistent individuality, selfhood, sentience, consciousness, or causal closure.

For new objective probe-suite evaluations, the score summary also retains
digest-keyed per-probe correctness or abstention outcomes across all five
conditions. It reports per-probe history transitions for A and B, outcome
agreement between models with and without history, and whether A's restored
arm reproduces its original per-probe pattern. This makes equal aggregate
counts distinguishable from agreement on the same probes. The probe input and
answer values remain out of this summary; the score artifact digest binds the
oracle-backed result. Older stored evaluations remain verifiable in their
original aggregate-only shape.

For calibrated v5 family-suite runs, the evaluation also compares Brier error
between history-present and history-withheld runs for each model, between A and
B under both history conditions, and between original and restored A. Each
comparison uses only the same probes where
both conditions have a scored integer answer and an integer confidence value;
it reports matched coverage and each side's Brier sum as well as the left-minus-
right normalized score difference. This overlap restriction makes missing
answers visible rather than treating them as zero confidence. The measure is a
paired score comparison, not a calibration diagnostic or evidence that either
model used the history. Prior summaries without these fields remain verifiable.

When this result enters bounded developmental-history projection, its
validated per-condition answered/abstained counts, coverage, and selective
accuracy remain available in a separate `selective_metrics` block with the
five-condition order stated explicitly. V4 also retains exact correct counts
per condition, allowing downstream readers to verify selective accuracy without
reconstructing counts from floating-point ratios. These measurements stay
distinct from correctness and do not assign utility to answering or abstaining.
The writeback projection binds each condition's score digest and recomputes
coverage and selective accuracy from answered counts and verified correct
counts before retaining them. That bounded writeback format uses projection
schema v5. It can also retain answer-free per-probe correctness / abstention
outcomes and exact restoration matches when the five score rows contain aligned,
coherent probe results. Each outcome row is a five-label vector in the declared
condition order. Probe input values and answers remain private. Rows use
within-suite indices rather than hashes derived from low-entropy probe values.
Prior v1/v2/v3/v4 projections remain verifiable in their original shapes.

Calibrated selective objective scores use score schema v6. The writeback score
contract binds the exact schema and each condition's score digest; it does not
project answer confidence values into developmental history. The projection
contract allowlist now accepts v6, preserving the task-plan/evaluator binding
and salted private-oracle commitment posture for calibrated family suites.

### Preregistered cross-range history (task contract v6)

The `rootless_integer_affine_transfer_wide_range_v7` target may declare an
ordered `history_task_family_ids` list in its v6 task specification. The list
is part of the salted task commitment and public descriptor. Every listed ID
must be a registered fixed-mapping family with the same declared mapping as
the target, and the target must appear in the list. This permits the v6
low-range acquisition family to supply historical evidence to a v7 wide-range
transfer task without changing historical family labels or broadening the
selector globally.

The owner selects records only when they contain facts tagged with one of the
declared source families. Each projected example retains its source family and
evaluator outcome. The task instructions treat only evaluator-correct rows as
mapping evidence; incorrect and abstained rows retain their distinct prior
outcomes. Probe overlap is audited across every declared source family. The
target evaluator continues scoring the independently sampled v7 probes.
Resident aggregation may combine score-bound correct rows across the declared
source families only when each source family is registered to the same fixed
mapping and its input remains inside that source family's registered range.
The derived provisional strategy carries the complete source-family list and
source refs in its digest-bound provenance.
This is an evidence-admission protocol, not evidence that a model learned or
transferred the mapping; inference and outcome comparison are still required.

The resident developmental capability remains **partial** with `bounded_state_transition` authority. Real resident A→B→A activation, serving handoff, default-cadence continuation, long-duration repeated trials, statistics, semantic scoring, training, autonomous model choice/acquisition, and identity claims remain deferred.

## Repeated trial identity

`run(trial_id=...)` accepts a bounded explicit identifier. It is included in run,
observation, and correlation identity only; corresponding semantic prompts and frozen
evidence remain byte-equivalent. Observations truthfully name the endpoint custody
field `authority_record_digest` (not the former misleading `authority_map_digest`).
The separately documented campaign reuses this experiment rather than duplicating its
five-condition logic.

## Local evidence inventory (2026-11-21)

A read-only audit of the local `sentientos-hermes-cognition-campaign-20261119`
store found no model-transition protocol or evaluation artifact under its
rootless developmental-cognition cycles. Its four cycle directories
(`rootless-cognition-cycle-14668649c4634fbeb3cc`,
`rootless-cognition-cycle-91ce4c4593054807a6e1`,
`rootless-cognition-cycle-dadc94d8bca0472ab004`, and
`rootless-cognition-cycle-07b41b23fcf74c09b38a`) contain incomplete-run
records, not A→B→A evaluations. The separate completed Hermes epistemic run
`rootless-epistemic-run-5aa30a4bda714ad189b23529` used one model artifact and
scored correction and pressure conditions; it did not replace the model. Its
integrity and outcome are recorded in
[`rootless_experimental_epistemic_series.md`](rootless_experimental_epistemic_series.md).

Accordingly, the local evidence inventory contains no empirical result for
cross-model continuity. A repository-wide artifact-name scan also found no
persisted calibrated family-suite model-replacement run to populate the newly
implemented paired Brier comparisons. The first applicable evidence must come
from the frozen five-condition A+H/A-H/B+H/B-H/restored-A protocol above, with
eligible source and runtime custody. The design and metric implementation alone
do not establish continuity or a history-associated confidence effect.

### Follow-up evidence inventory (2026-11-22)

A bounded read-only scan of the current follow-up workspace's
`sentientos-data/rootless-experimental` found no model-replacement run,
continuity, or transition JSON artifacts and no model-replacement experiment
directory. The repository artifact-name scan found construction acceptance
material, but no empirical replacement run. This scan does not cover a
production installation store. The five-condition A+H/A-H/B+H/B-H/restored-A
study therefore remains unrun in the inspected rootless workspace; no
cross-model behavior or continuity result is added by the current CPU-only
cognition work.


### Current follow-up inventory (2026-11-23)

A read-only check of the active WSL experiment store found that neither
`sentientos-data/developmental_experiments/model_replacement` nor
`sentientos-data/developmental_experiments/model_replacement_campaigns` exists.
The repository artifact tree contains the partial proof bundle, but no persisted
model-replacement protocol, run, campaign state, or report. The model-replacement
experiment, replication campaign, experimental-serving adapter, and one-shot
production-trial runner are implemented surfaces; their presence does not supply
empirical continuity evidence.

The inspected evidence state therefore remains partial. There is no persisted
A→B→A evaluation to score, and no cross-model continuity or developmental
learning claim is supported. This inventory covers the active rootless WSL
workspace and this repository's artifact tree; it does not inventory any
separate production installation store.

### Matched history-use preflights (2026-11-25)

The later Campaign87 Hermes and Campaign88 Qwen plans bind the same Cycle149
history boundary, the same 12 held-out transfer probes, and the same 2,521-file
implementation closure. Their owner preflights and exact-source replay are
verified in the [resident cognition evidence inventory](resident_developmental_cognition.md#campaign104-verify-the-matched-preflights-against-the-pinned-source).
The replay confirms plan, prompt, model-manifest, source, and history-boundary
construction without loading either model. Cycles176–179 remain unstarted.

These paired plans can measure how two distinct model targets respond to the
same retained history when inference is later run and independently scored.
They do not activate one resident model, hand serving to another, restore the
first model, or demonstrate that a developmental history survives an actual
resident transition. The five-condition A+H/A-H/B+H/B-H/restored-A transition
study remains a separate required experiment. Until either study has eligible
inference and scored outcomes, both durable cross-model history use and
resident cognitive continuity remain empirical questions, not established
properties of the architecture.

The CPU-only [runtime-preview parity audit](../../artifacts/experiments/resident-history-budget-campaign87-v8-hermes-12probe/matched_runtime_owner_preview_parity_v1.json)
further verifies that both target prompts received the same two score-bound
records and example evidence. The record-level prompt packets differ because
they add applicability metadata for each target identity. The public task
digests differ because each seeded task commits to a fresh private nonce,
although the registered family, generation seeds, backend seeds, and requested
probes match. Full prompt text is not exported. A future paired replication
can hold the commitment nonce constant across targets while keeping it private
in scoring custody. The parity audit independently reconstructs equal
nonce-free task specifications from the pinned generator and common seeds,
without publishing their oracle parameters. This narrows the current evidence
to matched retained examples and task inputs, not identical prompts or
attention.

### Identity-neutral prompt parity (2026-11-25)

The later [identity-neutral matched preflight](../../artifacts/experiments/matched-task-commitment-20261125-identity-neutral-v5/matched_prompt_parity_v4.json)
holds the private task commitment constant and removes the target identity
digest from the model-visible history projection. Independent replay confirms
equal selected records, equal withheld examples, and equal prompt digests in
both history-present and history-omitted arms for Hermes and Qwen. The exact
fact, task, source identity, and record bindings are checked against the
source-cycle records. This resolves the earlier input-parity gap for this
preflight protocol only; no model was invoked, and there is still no behavioral,
transfer, A→B→A, or durable-learning result.

The exercise is now reproducible from the repository tool
[exercise_model_replacement_context_v3_artifact.py](../../tools/exercise_model_replacement_context_v3_artifact.py).
Run it from the repository root with:

```sh
python3 tools/exercise_model_replacement_context_v3_artifact.py --output /private/path/context-v3-artifact-exercise-reproducible.json
```

A single CPU-only run on 2026-11-28 verified round-trip reload, ordered bindings,
absence of raw projection payload, all five tamper outcomes, and pristine reload
after each mutation. The report is
[context-v3-artifact-exercise-reproducible.json](../../../sentientos-data/rootless-experimental/model-replacement-v3-context-verification-20261128/context-v3-artifact-exercise-reproducible.json)
(mode 0600, SHA-256
`cc1ebef127f2ccf18bf7a0c5e1d858cb807e595fd1a45fd3f152e43b54c78948`). The tool
SHA-256 is `b0321cfa7588d5d8c761f5c4d9d8943ac7a4cb5e088fca4c2ec4d9b70ee0e886`.
It uses synthetic data, a temporary artifact store, and no model or GPU. As with
the original exercise, this verifies artifact reload integrity only; it is not
evidence of learning or semantic continuity.
