# Condition-isolated durable-learning protocol design

## Current status

Protocol v6 is the historical single-baseline format. Protocol v7 introduced
branch IDs and routed contexts; v8 preregisters consolidation and projection
policies. V9 freezes the signed exclusion-audit, prompt-template, and
strategy/control machinery but leaves probe consumption unregistered and
cannot run delayed probes. Opt-in v10 preregisters consumption and connects
that machinery to the runner, recovery, and finalization. Protocol v11 added
the withheld-history competence criterion. Protocol v12 is now the public
constructor default; it retains that gate and binds the complete historical
integer probe-input inventory. V8 and v11 remain explicitly selectable for
legacy protocol construction and verification.

V10 can execute only in explicitly enabled descriptive-only mode because the
protocol verifier deliberately leaves `retention_contrast_eligible=false`.
That flag must not be inferred from successful execution. V10 preregisters the
bounded projection-consumption policy. Protocol verification exposes its
digest alongside the slot-format, neutral-control, prompt-template, and
answer-exclusion policy digests; runtime gates and finalization bind the
consumption policy to prompts and receipts.
Opt-in protocol v11 adds a digest-bound minimum-correct-count criterion for
withheld-condition acquisition. The persisted owner-side assessment is
required before a delayed-probe start gate, invocation attempt, outcome, or
evaluation can be accepted. Independent outcome-set verification applies the
same qualification rule, and the retained-gate inventory reports incomplete,
missing, or present qualification evidence. V11 remains descriptive-only:
baseline competence does not show a history effect or establish durable
learning. V5-v10 protocol identities and historical evidence shapes remain
unchanged. New v12 construction requires its minimum withheld-acquisition
correct-probe count plus a resident owner from which the historical probe
inventory is derived. The exact prior input set and inventory digest are
frozen in the protocol, and protocol verification rejects overlap with either
task phase. V11 remains available with its original digest contract.
The assessment persistence check and delayed-attempt journal now share a
custody-root lock on Windows and POSIX. This serializes the check-and-publish
boundary across runner processes, preventing a delayed invocation attempt from
being journaled between the "no attempt exists" check and assessment write.
The lock serializes callers that use the governed store API; it does not
prevent out-of-band filesystem changes. It is not an external timestamp or an
independent attestation of preregistration timing.
Delayed attempt records currently bind the protocol and prompt, but do not
change their v1 identity. A separate immutable authorization receipt now binds
each V11 delayed attempt ID and digest to the exact qualification assessment
ID and digest. Attempt-journal recovery verifies the receipt against the
reconstructed assessment before accepting that attempt. This makes the gate
chain self-describing without rewriting the legacy attempt identity. The
[authorization schema](durable_learning_competence_authorization.schema.json)
defines its answer-free fields; the receipt still does not establish learning,
external timing, or protection against out-of-band filesystem changes.
The Windows experiment-store filename custody policy now explicitly accepts
the durable-learning protocol ID and the bounded durable-learning run artifact
prefixes, including this authorization receipt. This keeps the same immutable
publication checks active on Windows instead of rejecting experiment-native
names at the custody boundary.
The V11 retained-evidence inventory emits these receipt references under
inventory schema v5; older protocol versions retain schema v4. The
[`v5 schema`](durable_learning_persisted_gate_evidence_v5.schema.json) defines
the receipt references and explicit empty state. Inventory construction
reconciles the receipt count against journaled delayed attempts after validating
each persisted authorization artifact.
Expected acquisition and delayed-probe outcome totals derive from the canonical
condition count times the phase task count, so inventory totals track the
protocol's condition contract rather than a duplicated numeric constant.
V11 outcome-set and evaluation schema v34 carry the same authorization
references in the digest-bound report, and both independent verifiers require
the receipt artifacts as input. The earlier v33 assessment-only envelope is
not accepted for V11.
The production serving adapter inserts the exact rendered user turn with
`retain=false` and submits only the guarded `effective_prompt` to the governed
invoker. Its pre-effect guard checks the prompt digest against its bound gate, so
the conversation transcript is not silently replayed as model context by this
adapter. V10 uses gate v4 to also bind the persisted branch-preflight artifact.
This verifies the request path; it does not prove process isolation or
the model's causal reliance on the supplied strategy.
Condition-state isolation, independent filesystem/process custody, external
timing, scorer separation, causal use, and durable learning remain
unestablished. The gates prove that the registered prompt and branch evidence
were bound to an invocation; they do not prove the model relied on the strategy
or improved because of it. Earlier v7/v8 prompts lacked the v9 strategy slot;
that historical limitation is not the current v9 prompt contract.

The V10 branch-preflight preparation now also captures one bounded,
handle-relative inventory of each AppContainer profile's regular-file tree
and persists it as an immutable artifact bound to the protocol, branch
preflight, and profile-pair artifacts. A protocol-specific paired baseline
pins the first two inventory artifact references; repeated preparation rejects
profile-tree drift instead of silently treating it as the same setup. The
inventory includes file content
digests and filesystem identities, but does not establish writer quiescence,
an atomic snapshot, alternate-stream coverage, registry-state coverage, or
profile-state accounting. These observations make profile-local persistence
visible for later analysis; they do not qualify the retention contrast or
enable mutation. Their schema is
[`durable_learning_profile_data_inventory_artifact.schema.json`](durable_learning_profile_data_inventory_artifact.schema.json),
and the paired baseline is specified by
[`durable_learning_profile_data_inventory_baseline.schema.json`](durable_learning_profile_data_inventory_baseline.schema.json),
with the nested profile and regular-tree formats specified by
[`windows_appcontainer_profile_data_inventory.schema.json`](windows_appcontainer_profile_data_inventory.schema.json)
and [`windows_custody_regular_tree.schema.json`](windows_custody_regular_tree.schema.json).

The read-only epistemic proposition trace reconstructs active evidence after
each update generation, including explicit removals, and checks that state and
receipt custody remains unchanged during inspection. It binds the resulting
prior projection to the selected proposition and rejects inconsistent evidence
posture. This makes membership transitions inspectable alongside state digests
and mutation receipts; it remains provenance only and does not establish truth,
causal reliance, or learning.

## Relationship to neighboring cognition experiments

The persisted proof bundle for the resident history intervention is marked
`partial`: it supports a bounded present/withheld/restored intervention, while
explicitly leaving improvement, learning, and model-independent persistence
unproven (`artifacts/proof_bundles/developmental_history_intervention_experiment.json`).
The model-replacement proof bundle is also `partial`; it covers frozen same-state
dual-model substitution, ablation, and restoration, while production activation
and long-duration inference remain deferred
(`artifacts/proof_bundles/developmental_model_replacement_experiment.json`).

Semantic history retrieval is implemented as a production selection path, but
its experiment status says independent relevance labels and Phase A results are
not yet available. Response effects and durability are gated on those results
(`docs/development/semantic_developmental_history_retrieval_experiment.md`).
The durable-learning branch experiment addresses the intervening question of
whether a receipt-bound developmental update can later be consumed by cognition;
it does not replace the retrieval-quality or model-replacement experiments.

## Protocol v7 and v8 contracts

Protocol v7 currently derives two distinct branch IDs from the protocol nonce
and condition names (or accepts explicit branch IDs). This binds branch names,
but does not prove that backing stores or sessions are isolated. A retention
study still needs the complete condition-specific state plan:

The read-only `DurableLearningConditionBranch` descriptor and
`verify_durable_learning_condition_branches(...)` preflight now check that the
two resident owners are distinct, their resolved state roots refer to distinct
filesystem objects and are non-overlapping (neither is an ancestor of the
other), each active session ID is distinct, and both owner and runtime
snapshots exactly match the protocol's frozen baseline inventory. This
establishes local setup consistency only; it does not prove process or
filesystem access isolation. The verifier's v5
report exposes `configured_state_roots_non_overlapping` and
`configured_state_root_objects_distinct` separately from
`filesystem_isolation_independently_attested=false`. The runner now accepts
exactly two branch descriptors for v7 and routes
each condition's experience source, prompt/probe snapshot resolver, and
executor through its own descriptor. It attaches the preregistered branch ID
to the governed request linkage, and the receipt verifier checks that binding.
For v10, the first baseline preflight is sealed as an immutable protocol-bound
v6 artifact before acquisition. It requires both active conversation sessions
to have empty transcript turn lists and records that baseline fact alongside
digests of each resolved branch state root, conversation-store root, writeback
store root, and session ID, not raw paths. V10's production factory can route the conditions
through distinct conversation stores; preflight rejects shared store objects,
overlapping roots, and any overlap among either session-store root and either
branch state root, including filesystem aliases. This
prevents unregistered prior conversation history from entering either arm.
Branch verification also requires distinct writeback controller and store
objects, resolves both writeback roots, rejects aliased or overlapping
writeback roots, and rejects writeback roots that overlap either arm's
conversation store or the opposite arm's state root. V10 seals both writeback
root identity digests in preflight v6 and requires them to match during delayed
probe admission. These are local custody checks; they do not turn the preflight
into an independent filesystem attestation.
It also enumerates each bounded session store and requires exactly the
condition's registered branch session in it, so an unrelated prior transcript
cannot remain hidden in an otherwise separate store root. Every later
preflight repeats the inventory check and compares live roots and session IDs
with the artifact, including delayed probes after consolidation;
evaluation reload also verifies the sealed artifact's identity and contents.
This detects setup drift within the local custody boundary; the artifact is
not an independent filesystem or process attestation. Acquisition still
requires the frozen baseline, while delayed probes recheck branch bindings
without requiring post-acquisition history to equal baseline.
The delayed-probe report verifier also requires the current snapshots to match
their owner sources and checks the expected post-baseline status fields before
accepting the sealed identities. This prevents a structurally plausible but
incomplete caller-supplied report from standing in for a successful live
branch preflight; the report is still produced within the same process trust
boundary and is not independent attestation.
`retention_contrast_eligible` remains false because v7 delayed probes do not
consume branch-specific strategy projections. Consolidation writebacks and
their typed projection artifacts can now be receipt-bound, but that artifact
alone does not prove later cognition used it.
Protocol v8 now preregisters digests for the fixed consolidation and strategy
projection policies. Its verifier reports those policy bindings separately
from projection consumption. Consolidation receipts and the run summary now
report the consolidation policy as preregistered for v8, and receipt reload
checks that claim against the protocol version. Projection consumption remains
unregistered, and `retention_contrast_eligible` stays false.
The v8 contract does not yet put the projection into a delayed-probe prompt.
Its delayed-prompt digest binds the complete canonical prompt, so adding a
projection after protocol creation would invalidate that binding and violate
the frozen protocol.
The branch-aware production factory builds one persisted context and governed
executor per condition and routes receipt reconstruction by protocol branch
ID. Legacy branch protocols may share a session store; V10 can receive a
condition-to-store mapping and uses each store for both transcript writes and
receipt reconstruction. Construction is inert:
it does not create sessions, invoke inference, score outputs, or write back
developmental state. The caller must provision two active sessions, distinct
resident owners and roots, and matching baseline snapshots before the first
acquisition can pass preflight. Routing reads branch IDs from the canonical
protocol verifier, which normalizes the IDs preregistered under
`condition_contract`; the request receipt is checked against the same mapping.

`provision_durable_learning_condition_sessions(...)` provides the explicit
setup step for fresh V10 stores. It takes both resident state roots, two new
conversation-store roots, and the session model identity; it creates two empty
active sessions and returns the store and session-ID maps for the runtime
factory. It rejects existing session roots and overlapping configured roots
before creating either store, including dangling symlinks at the requested
session-store paths. The symlink check is performed on each requested path
before resolving it, so a dangling link cannot disappear from the freshness
check when its target does not yet exist. Filesystem failures during creation
can still leave partial empty setup state;
`DurableLearningConditionSessionProvisioningError`
preserves the stores and session IDs created before failure so they can be
inspected before recovery or retry. This helper does not run inference or
certify the identity of a later
serving model. Add each returned ID to its matching `condition_configs` row,
then pass the returned stores as `condition_session_stores` to
`create_production_durable_learning_branch_runtime(...)`.
After persisting the protocol and constructing the runtime, call
`runtime.runner.prepare_condition_branch_preflight(protocol)` to produce the
live branch verification and seal/reload the V10 baseline artifact before any
acquisition inference. Its report marks `inference_started=false` and
`scoring_started=false`, `developmental_writeback_started=false`, and
`authority=false`; it establishes setup readiness, not learning.

## Existing writeback seam

The current resident writeback path cannot be invoked by passing a Phase C
transcript receipt directly. `ResidentDevelopmentalWritebackController`
accepts candidates grounded in typed resident cognition observations, and its
history-conditioned candidate constructor revalidates the observation,
selected evidence, exact output text, and local-model receipt. The resident
cycle obtains that candidate from its own cognition observation path and then
uses the writeback controller's separately admitted append operation.
`run_companion_interaction` explicitly returns without writeback. Meanwhile,
the Phase C serving executor stores receipt-linked chat turns but does not
create a resident cognition observation. The consolidation runner now adds a
governed bridge that turns branch-local acquisition evidence into a typed
resident observation and candidate, while preserving branch attribution and
excluding scorer outcomes under the current no-feedback policy. The withheld
arm uses a distinct no-history observation contract. Calling the writeback
controller with a hand-built or transcript-only candidate would bypass its
provenance contract and remains disallowed.

The Phase C runner now has a read-only preparation step that reconstructs each
branch's acquisition turns from its receipt-bound session and builds a typed
World-State snapshot. Prompt and response facts carry the branch, task,
receipt, prompt/output digests, and exact turn text. Only acquisition material
is included; scorer scores and attestations are excluded, and preparation is
limited to the preregistered no-feedback policy. The new source kinds are
`developmental_experiment_input` and `local_model_output`, both non-authority
evidence. The runner journals branch ticks, reloads their observations and
writebacks, and seals consolidation receipts; these operations remain
descriptive under v7.

The resident owner now accepts an explicit `withhold_developmental_history`
flag on `run_tick`. It verifies the owner's retained inventory, then supplies
an empty history projection to that tick. The prepared bundle binds the
available branch to normal branch history and the withheld branch to this
suppression mode. The runner now has an explicit
`run_branch_consolidation_ticks(...)` operation. It journals both branch
intents before each tick, calls the resident owner with the branch's source
snapshot and history policy, reloads the owner's writeback receipt and state
inventory, and seals a consolidation receipt. On restart it recovers completed
ticks, runs only an intent whose owner confirms the tick never started, and
fails closed on an interrupted tick. Protocol v7 still does not preregister
this consolidation policy, so this operation is descriptive-only and does not
open the retention gate. v7 delayed probes now require both verified
consolidation receipts.

1. **Paired baseline branches.** Freeze distinct branch IDs for the
   experience-available and experience-withheld conditions. Verify both
   branches start from the same record and receipt inventory digest, then bind
   their separate branch identities and state roots in the protocol. A branch
   must not share a mutable history store or conversation session with the
   other arm.
2. **Routed acquisition.** Route each task, prompt guard, receipt context, and
   stored transcript to the scheduled condition's branch. The available arm
   may expose only the frozen experience record references. The withheld arm
   must expose none. Both arms use the same task set, model identity,
   generation configuration, feedback policy, scoring rubric, and
   counterbalanced schedule.
3. **Explicit consolidation.** After all acquisition outcomes are persisted,
   run one preregistered developmental update per branch through an admitted
   resident writeback path. Bind the update to that branch's exact acquisition
   receipts, selected experience references, scoring policy, updater identity,
   and update receipt. The updater must not read the other branch or silently
   turn a no-feedback model policy into answer feedback. Any scoring-derived
   information available to the updater is itself part of the frozen policy.
4. **Derived strategy projection.** A stateless serving model cannot use a
   hidden database change unless the cognitive system projects that change
   into behavior. Bind the exact derived strategy or procedure projection
   consumed by later cognition. Delayed prompts must exclude raw acquisition
   dialogue and exemplar answers while including only the branch's verified,
   bounded strategy projection. Apply the same projection slot and neutral
   control procedure in both arms so the intervention is attributable to the
   learned content rather than prompt shape or token budget.
5. **Branch-routed delayed probes.** After the frozen delay, route each probe
   to its condition branch and strategy projection. Use disjoint task inputs
   and new surface forms. The receipt must bind branch ID, branch-state digest,
   strategy-projection digest, and exact prompt digest. Probe calls must not
   inherit the acquisition transcript.
6. **Independent attribution.** Before scoring any retention claim, re-open
   each branch, verify its baseline and update receipts, prove the strategy
   projection derives from that branch's admitted acquisition evidence, and
   verify that delayed behavior used the bound projection. Score probe outcomes
   blind to condition. Keep correctness, abstention, calibration, state
   restoration, and source attribution as separate outcomes.

## Eligibility rules

The outcome report v30 retains the equal-weight declared-family macro for
continuity and adds per-family strata split by task schema version and
`requires_task_family_history`. The pooled macro can combine variants across
those strata, so it remains descriptive; inspect the strata to see whether an
effect is limited to one scoring contract or history requirement. Ungrouped
tasks remain excluded from the family macro and are counted separately. These
summaries compute no confidence interval, population uncertainty, or learning
claim. The transfer-structure report now shows acquisition and delayed-probe
input occurrence counts, unique input counts, and cross-phase overlap counts,
including for each shared declared family. This reveals repeated inputs within
a phase separately from the disjointness check. It verifies numeric input
disjointness but does not establish task equivalence or causal transfer. The
family macro also includes leave-one-family-out sensitivity ranges and whether
the favorable direction survives every single-family omission. This is a
robustness diagnostic over the declared fixture families, not a confidence
interval or population estimate. A phase-trajectory summary compares each
shared family/schema/history-requirement stratum's contrast during acquisition
with its contrast on delayed probes. It reports metric counts, means, and the
change toward or away from the preregistered favorable direction. Those phases
use disjoint task inputs, so the trajectory is a descriptive between-phase
change, not a paired task-level retention estimate. Persisted v29 evaluations
remain verifiable by omitting the trajectory; v28 evaluations also restore
their prior family-macro shape, v27 their metadata-only transfer report, and
v26 their pooled-only family-macro shape.

The retention gate may become true only when all of the following are bound
before inference and verified after it:

- two distinct persistent branch identities with equal verified initial state;
- condition-routed sessions, history sources, and state snapshots;
- an admitted and receipt-bound post-acquisition update in each branch;
- a policy that specifies exactly which acquisition evidence each updater may
  use, including whether scorer outcomes are available;
- branch-specific strategy projections that exclude raw acquisition answers;
- delayed probes that consume the correct projection and no acquisition chat;
- independent score verification and complete paired probe outcomes.

If either branch is missing, the branches share mutable state, consolidation
did not occur, or the strategy projection cannot be tied to its source
evidence, the run remains descriptive and `retention_contrast_eligible` stays
false. These conditions qualify an experiment design; satisfying them still
does not establish learning. Durable development requires measured improvement
on the preregistered disjoint probes and evidence that the retained strategy
changed later cognition. Model-replacement continuity requires another
experiment.

## Implementation sequence

1. Add a read-only branch inventory verifier for two resident owners and
   distinct active session IDs, requiring identical baseline inventories.
2. Protocol v8 binds fixed consolidation and strategy-projection policy
   digests before any model call. Opt-in v10 preregisters bounded projection
   consumption and wires it through the runner and delayed-probe gate. V10
   also persists local branch-root, session identity, and per-condition
   conversation-store root identity digests. Its production branch factory
   accepts separate stores for the two conditions; preflight rejects shared,
   overlapping, or aliased roots and binds the v5 preflight artifact into each
   v4 gate. These checks establish local configuration consistency only.
   Independent filesystem/process custody remains outstanding; the stores
   share the same serving controller and host process, and local path checks
   do not attest external isolation.
3. Add condition routing to the Phase C runner, receipt resolver, and inert
   production runtime factory; preserve v5/v6 reconstruction for historical
   protocols. **Wiring is implemented; an execution of the V10 path against
   provisioned branch stores and sessions remains outstanding.**
4. Add a governed branch-local observation-to-writeback bridge. It must create
   typed resident cognition observations from exact branch-local acquisition
   evidence, use the existing candidate verification and admission path, and
   return a bounded immutable receipt that is reloaded before delayed probes.
   Receipt-verified snapshot preparation, condition-scoped resident ticks,
   writeback reload, restart-safe runner journaling, and an explicit typed
   no-history consolidation observation are implemented. The withheld tick
   requests a bounded lesson packet grounded only in current acquisition facts;
   its observation records that no developmental history was projected, and
   its writeback candidate is reloaded through the existing evidence and
   admission checks. A deterministic projection resolver now derives a bounded
   strategy object from a reloaded typed writeback and seals it into a v2
   consolidation receipt. The projection schema copies no raw turn text,
   source output field, fact payload, score, or attestation. It does not
   verify semantic answer-example exclusion, so it is explicitly ineligible
   for probe use. A conservative exact-text guard rejects strategy text that
   repeats a selected local-model output or the exact `answer`/`answers` field
   derived from the frozen acquisition task plan; short model outputs use token
   boundaries so single-number answers are checked without matching the same
   digit inside a different number. This guard does not establish that a
   generalized lesson is free from paraphrased answer leakage. Its evidence
   dependencies and contradiction references must now all resolve to
   acquisition facts or prior records in
   the same typed observation, and at least one dependency must point to a
   current acquisition fact. Every selected fact must also be unique and
   present in that observation's current facts. Reloaded consolidation
   receipts independently enforce unique source and selected fact IDs, with
   every selected ID drawn from that receipt's source snapshot, even if no
   projection was produced. The receipt label, tick intent label, and
   protocol-bound branch ID must now all resolve to the same condition.
   Receipt reload also requires writeback-selected
   facts to occur in the reloaded tick observation; a no-writeback receipt
   cannot claim selected facts. Every projection's source observation ID and
   digest must match exactly one observation in the sealed tick receipt. The
   history-available projection also requires nonempty, unique retrieved
   record IDs paired one-to-one with SHA-256 record digests; the withheld arm
   still requires both lists empty.
   New consolidation intent v2 artifacts store the full baseline record and
   receipt references, and their digest must recompute to the protocol's
   frozen baseline state digest; intent v1 remains readable with its exact
   legacy reference shape but cannot prove the receipt-level baseline binding.
   Current
   intents and v2 receipts reject unknown or missing fields, while the legacy
   v1 receipt reader remains available. Receipt reload binds the intent's own
   branch ID as well as the receipt's branch ID to the protocol condition. The
   projection is not consumed by v7 probes, and the update policy is not
   preregistered. Consolidation now
   verifies append-only state against both
   the sealed baseline and the reloaded post-tick inventory; every baseline
   record ID and digest must remain unchanged, while new records must still
   match the single attributed writeback. The withheld observation must also
   show no self-model claims, epistemic state, or consumed/omitted epistemic
   packets, in addition to no developmental records. The available tick now
   receives an owner-validated allowlist of preregistered target experience
   records. Its observation must contain paired refs from that allowlist and
   frozen baseline, with no other prior cognitive context. Both
   inventories are canonicalized by record ID, and a baseline cannot mix
   legacy and full reference shapes. The target-experience resolver rejects
   duplicate resident record IDs within any one acquisition task, so a single
   admitted record cannot stand in for multiple preregistered examples.
   Strategy projections now have a standalone integrity verifier for exact
   fields, branch and protocol bindings, evidence references, and the sealed
   digest. The verifier also reloads the referenced writeback receipt and
   cognition observation from that branch owner and binds their IDs, digests,
   selected facts, and condition-scoped history exposure to the projection.
   The runner invokes it before receipt persistence and after rebuilding a
   projection from reloaded writeback evidence. This proves lineage and
   artifact integrity, not answer-example exclusion or causal use; those and
   probe eligibility remain false.
5. Protocol v9 was an opt-in preregistration schema and retains its original
   digest contract. The public constructor now defaults to v12, which carries
   the withheld-acquisition competence gate and historical-probe inventory
   binding. Explicitly selected legacy versions retain their original digest
   contracts. V9 freezes digests for the strategy
   slot, neutral control, projection-consumption policy, and exclusion-audit
   policy, and requires a distinct Ed25519 exclusion-auditor identity and
   software digest before protocol creation. This registers the auditor key,
   not an audit result; v9 rejects reusing the scorer key or software digest.
   A blinded audit-request builder now supplies scoped strategy content,
   acquisition inputs and expected outputs, and selected acquisition model
   outputs under one protocol-scoped subject ID shared across branch contexts.
   The identifier is not derived from a branch ID, which is published in the
   protocol. A signed pass/fail/inconclusive
   attestation binds the request, projection, example-set digest, protocol,
   and preregistered auditor identity. Verification rebuilds the request from
   branch evidence and checks the Ed25519 signature. The request excludes
   condition/branch labels and delayed probes; it does contain acquisition
   answer examples for the independent auditor. This signature records the
   auditor's claim, not the truth of that claim. The new answer-exclusion
   policy v2 digest binds this protocol-scoped subject rule; public protocol
   creation uses v2, while v1 remains available only to reconstruct existing
   protocols and verify their branch-derived IDs. The portable v2 signature
   check enforces the protocol-scoped ID; the full artifact verifier binds v1
   IDs back to their branch. V9 also preregisters
   per-condition, per-task prompt-template digests. The renderer and verifier
   insert an available-arm projection only after a signed pass; the withheld
   arm receives the fixed neutral control. The renderer and v3 pre-effect
   guard remain inert, verifiable machinery in v9. V9 keeps
   `projection_probe_consumption_preregistered=false`; its historical digest
   remains unchanged and the runner rejects its delayed-probe phase. Protocol
   v10 retains the v9 evidence fields, sets consumption preregistration true,
   and enables the runner path. The guard rechecks both branch receipts, the
   acquisition outcomes, projection/audit evidence,
   prompt digests, delay, and retained-state refs immediately before opening.
   Strategy gates can now be persisted and reloaded against branch artifacts,
   and delayed-outcome verification binds the dynamic prompt digest to that
   gate. V10's v4 gate also binds the immutable preflight artifact ID and digest;
   finalization and evaluation require the exact same reference.
   Outcome-set verification also checks gate acquisition refs and completion
   times against the verified paired acquisition records. The v10 runner
   reloads paired acquisition and consolidation evidence,
   rebuilds the blinded audit request, accepts the available arm's signed pass
   attestation on first use and reloads the unique immutable artifact on
   subsequent calls, renders each registered prompt, and
   persists the answer-free signed audit artifact and a v4 gate bound to the
   persisted branch-preflight artifact before
   journaling the invocation attempt. Finalization reloads that immutable
   artifact, rebuilds the blinded audit request, revalidates the auditor
   signature and each condition's exact registered prompt, and checks those
   digests against the persisted outcomes and gates. Evaluation reload also
   reloads the protocol-bound branch preflight artifact and rechecks its
   canonical digest, branch mapping, root/session identity digests, and
   fail-closed isolation posture. It also rechecks the stored request's
   canonical digest, expected acquisition
   examples, example-set digest, projection content, signature, and linkage
   to the outcome gates and current persisted consolidation receipt refs. It
   also requires v2 consolidation receipts and checks each receipt's condition,
   branch, intent identity, and strategy-projection digest against the paired
   persisted intent and protocol branch map before accepting the gate refs.
   Reload checks the projection's canonical identity, writeback refs, source
   fact binding, bounded strategy fields, and explicit no-authority,
   no-adoption, and probe-ineligible flags for both conditions. It
   cannot independently rebuild selected source
   outputs without the branch-local writeback owner; finalization performs
   that stronger source check. This remains
   descriptive-only because v10 is not retention-contrast eligible. For an
   interrupted invocation, the runner rebuilds the prompt from the reloaded
   signed audit evidence, asks the receipt verifier for a transcript-committed
   completion, reloads the persisted v4 gate against the current branches and
   consolidation artifacts, and requires the recovered guard evidence to
   equal that gate before reconstructing an outcome. Missing completions or
   any prompt, gate, receipt, or state mismatch remain unresolved and fail
   closed. Across probes, the available arm receives the same sealed projection
   for every probe; the withheld arm receives a preregistered neutral control
   with the same slot boundary and no strategy advice. Neither prompt may contain
   acquisition turns, source outputs, answer keys, or scorer material. The
   independent exclusion auditor receives the scoped strategy content with its
   branch and condition identifiers withheld, an opaque audit subject, and the
   acquisition examples from scoring custody. It does not receive delayed
   probes or probe answers. Its signed attestation binds the protocol digest,
   opaque audit subject, projection digest, acquisition-example-set digest,
   auditor identity and software digest, and a pass/fail result; the verifier
   deterministically binds the opaque subject to the branch. The attestation
   records no answer text.
   Immediately before each delayed probe, reload and verify both branch
   receipts, the condition's projection, and the exclusion attestation. Render
   the exact condition-specific prompt and have a v4 pre-effect gate bind its
   digest, the projection or neutral-control digest, attestation digest, both
   consolidation receipt refs, branch-preflight artifact identity, task digest,
   acquisition completion refs,
   minimum delay, and retained-state refs. The governed invocation receipt
   must point to that gate. Reuse one projection and one exclusion attestation
   across all probes within a branch; never tailor the strategy to an upcoming
   probe. Any missing, ambiguous, or failed exclusion result keeps the run
   descriptive and prevents sending the projection to the model.
6. Enable `retention_contrast_eligible` only for this complete versioned path.

This design does not authorize unrestricted self-modification, direct action,
or automatic adoption of proposed strategies. It specifies an evidence path
for testing whether a bounded, admitted update changes later cognition.

## Next enabling boundary: condition workers

The current branch runtime constructs both resident owners, history sources,
conversation contexts, and executors in one Python process. V10's separate
roots and stores are useful setup checks, but they do not prevent that process
from opening either condition's files. A PID field, a second executor object,
or a worker thread would not close this gap. Keep
`conversation_store_process_isolation_verified=false` and
`retention_contrast_eligible=false` until an enforced boundary exists.

The next implementation must move branch-owned state and operations behind one
worker boundary per condition:

1. A supervisor owns the frozen protocol, condition schedule, audit artifacts,
   score coordination, and final report. It must not retain either branch's
   resident owner, writeback store, conversation store, or raw state path.
2. Each worker starts from a sealed condition configuration and owns exactly
   one resident owner, state root, writeback root, session store, and active
   session. The worker exposes a fixed, versioned RPC surface for baseline
   inspection, acquisition receipt recovery, consolidation, strategy-projection
   reconstruction, and delayed-probe gate inspection. It must not accept an
   arbitrary path or callable from the supervisor.
3. The operating system must enforce each worker's file access. On Windows,
   use distinct restricted principals or an equivalent kernel-enforced
   per-worker capability; on Linux, use distinct credentials plus a filesystem
   namespace or equivalent access-control boundary. Merely launching two
   processes under the same unrestricted user does not qualify. The serving
   controller remains a separately governed broker and receives only the
   exact gate-approved prompt and branch linkage.
4. Bind worker startup to the protocol and condition, executable/runtime
   identity, restricted principal, state-root identity, IPC endpoint, and a
   fresh process-start nonce. The worker returns evidence through the
   authenticated local channel; the supervisor verifies it against OS-observed
   process and access-control state. A worker self-report is not an
   independent attestation.
5. Before acquisition, run a no-inference isolation preflight. It must verify
   that each worker can read and write its own test sentinel, cannot open the
   peer's sentinel or state root, cannot access supervisor scoring custody,
   and that the supervisor cannot call branch internals except through the
   registered RPC. Preserve the OS error/result evidence, principal and object
   identities, worker startup evidence, and exact preflight digest. Any
   unexpected access or missing evidence fails closed before model inference.
6. Exercise worker crash and restart recovery with immutable intent and receipt
   artifacts before enabling delayed probes. Recovery must reconnect to the
   same branch identity, reject a new or overlapping root, and never replay an
   invocation whose completion is ambiguous.

The versioned wire boundary is specified in
[`durable_learning_condition_worker_rpc.schema.json`](durable_learning_condition_worker_rpc.schema.json).
The CPU-only
[`durable_learning_condition_worker_rpc.py`](../../sentientos/durable_learning_condition_worker_rpc.py)
validator enforces the same closed envelopes, checks response/request
correlation, copies each validated payload into a detached snapshot, and
requires the process-start nonce supplied by the supervisor's transport
observer. Its bounded UTF-8 JSON codec rejects duplicate keys and non-JSON
constants, then routes envelopes through the closed validator. It limits
requests to the registered operations; each operation has a closed
payload made of protocol-bound digests, task identifiers, and policy
identifiers, with no path, callable, or arbitrary command field. Responses
bind the request ID, branch, protocol, and process-start nonce, and expose a
result digest rather than raw state. This is an interface contract only: a
valid envelope does not authenticate the process, prove the nonce came from the
current worker, establish access restrictions, or qualify a retention result.
The supervisor must still verify process identity and access-control behavior
through OS observations before treating any response as branch evidence.

### Windows implementation target

For the current Windows host, the candidate boundary is one AppContainer
identity per condition worker, launched with the documented
`CreateProcessW` + `STARTUPINFOEX` security-capabilities path. The package SID
must be unique to the protocol run and condition. Grant the worker read-only
access to its executable/runtime and experiment code, and read/write access
only to its own branch state and IPC endpoint. Do not grant network capability
or inherited handles. Microsoft documents AppContainer file, registry, and
process isolation, and its launch guidance requires the security-capabilities
attribute; the effective file access also depends on the package SID and the
resource ACLs. See [AppContainer isolation](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation),
[launching an AppContainer process](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer),
and the [`SECURITY_CAPABILITIES` structure](https://learn.microsoft.com/en-us/windows/win32/api/Winnt/ns-winnt-security_capabilities).

[`windows_appcontainer_process.py`](../../sentientos/windows_appcontainer_process.py)
now provides the first native launch primitive. It uses a caller-provisioned
AppContainer package SID (the launcher and ACL helper both reject other SID
families), an explicit environment, zero requested capabilities,
`bInheritHandles=FALSE`, and a suspended `CreateProcessW` launch. It must join a
job object with a one-process limit and kill-on-close before it can resume.
Windows job objects enforce active-process limits, and the kill-on-close flag
terminates associated processes when the final job handle closes
([Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[`JOBOBJECT_BASIC_LIMIT_INFORMATION`](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information)).
Before resuming the worker it observes the process token's AppContainer flag
and SID, the enabled-capability count, process ID, and creation time. This is
launch evidence only: it does not grant the worker access to its runtime or state,
authenticate an RPC endpoint, prove that the requested executable digest is
the image Windows loaded, or verify denied peer access. The supervised durable
learning runner is now wired to launch the paired workers, exchange the access
matrix RPC, perform supervisor-side sentinel readback, and persist the paired
probe artifact. The completion and setup artifacts deliberately keep process
isolation, filesystem isolation, and retention eligibility false. This path
has not been run with live Windows ACL changes or worker launches, so its
implementation is not evidence that effective access restrictions have passed.

[`windows_appcontainer_access.py`](../../sentientos/windows_appcontainer_access.py)
adds an opt-in ACL primitive for an existing directory whose Windows file
identity was captured in advance. It merges two package-SID allow ACEs: one
for the directory and one inheritable by files. The `runtime_read_execute`
policy grants read/traverse/execute; `branch_state_modify` grants bounded data
and directory mutation rights without execute, DACL, or ownership changes.
The handle-custody verifier can retain these permissions only for the exact
AppContainer SID passed by the caller, and rejects package grants outside its
bounded mask. This verifies the named ACE structure and target directory
identity only. It does not measure effective access, prove peer or supervisor
denial, verify inherited ACL behavior on descendants, or establish retention
eligibility. The durable access-probe launcher now invokes this helper with
caller-curated runtime roots, after the persisted profile pair is verified and
before either worker is launched. It pins every root identity before the first
ACL mutation, rejects overlapping roots, and stops before launch if any
requested grant fails. Both the launcher and the lower-level pipe runner verify
the paired manifests before ACL mutation, RPC exchange, and completion sealing.
They require the own/peer sentinels to be exact reciprocals and the scorer
sentinel to match, then reject any runtime root whose resolved tree overlaps a
directory holding one of those sentinels. This prevents inconsistent target
sets and inherited runtime grants crossing into sentinel custody through a
broad or nested root. The check is a local preflight over supplied paths; it
does not establish effective isolation or replace the later worker access
matrix. These grants persist; the setup report and paired
artifact bind the requested ACE evidence to each root identity and profile SID,
but do not prove effective access, peer denial, or that the selected roots
contain every runtime dependency. A partial grant now produces a separately
sealed `runtime_access_attempt` artifact bound to the protocol, branch
preflight, profile-pair artifact, each root identity, and each applied or
failed grant. Failed entries distinguish a grant not attempted, uncertain API
outcome, reported API failure, API success without completed readback, and
verified ACL structure followed by another operation failure. Its artifact ID
is returned with the incomplete supervised-run report, and the store can
reload and verify it. This preserves evidence of partial persistent ACL
mutation while keeping it distinct from a completed
paired worker-probe artifact. No live Windows ACL grant or worker launch has
been performed while implementing this path. Before any later launch with the
same protocol, the runner reloads and verifies prior attempt artifacts and
returns `prior_runtime_access_attempt_unresolved` without changing ACLs or
launching workers. It also rejects a second probe after a completed paired
artifact exists, and a per-protocol Windows mutex serializes the full setup,
worker, and persistence lifecycle across supervisor processes. An abandoned
mutex indicates an interrupted run and remains quarantined for that protocol;
the caller must reconcile persistent grants and start a newly provisioned
protocol/profile pair. This path does not remove ACLs.
If cancellation interrupts the ACL API before its per-root report is returned,
the protocol is quarantined but no per-root setup artifact can be produced;
that case requires an ACL inventory during reconciliation.
If cancellation interrupts the ACL API before its per-root report is returned,
the protocol is quarantined but no per-root setup artifact can be produced;
that case requires an ACL inventory during reconciliation.
Failures after runtime grants and before paired completion now persist a sealed
worker-interruption artifact with the failure phase, supervisor-observed worker
identity summaries, endpoint conditions returned by the launcher, accepted
pipes, and cleanup outcomes. If the launch helper fails before returning, the
record marks that launch outcome and retains only what the supervisor observed;
the helper's internal partial-launch cleanup remains part of its own failure
path. The raised
`DurableLearningAccessProbeInterruptedError` carries that artifact identity.
If interruption evidence itself cannot be persisted, the active protocol mutex
is deliberately left owned so the protocol cannot silently be retried.
Runtime-directory identity capture permits existing read grants while checking
the volume-to-root ancestor handles for untrusted replacement/write rights;
private branch roots continue to use the stricter private-ACL check.

[`windows_appcontainer_access.py`](../../sentientos/windows_appcontainer_access.py)
now defines a closed, digest-bound probe manifest and worker-side no-inference
sentinel probe. The pipe-aware launcher can bind one manifest per condition
into the exact startup environment; the worker bootstrap rechecks its protocol,
condition, and AppContainer SID. The `probe_access_matrix` RPC attempts
read/write/flush on the worker's own sentinel and attempts read/write access to
the peer and scorer sentinels, recording exact Win32 errors and file identity.
The own-sentinel rewrite is attempted only after the opened file identity,
baseline content digest, and end-of-file check all match the frozen manifest.
This remains a worker report, not independent isolation proof. Supervisor
comparison with the expected report digest and independent post-probe sentinel
identity/content checks are still required. The pipe supervisor now has
`verify_condition_worker_access_probe_after_exit(...)`, which observes exit
through the launched worker's owned process handle, re-observes PID and
creation time through that handle, compares the exchange to the observed
identity, and then runs the read-only check over all three pinned sentinels.
New completion schema v3 persists the worker's returned result digest, the
expected matrix digest, and a bounded supervisor launch observation containing
the AppContainer SID, PID/creation time, capability/handle posture, process
nonce, executable digest, environment digest, and job binding. The completion
builder requires that observation to match the still-open process handle;
paired-artifact reload checks it against the profile SID and completion PID /
creation time. Schema v2 and legacy v1 completions remain readable, but they
do not carry this launch-observation linkage.
The completion report leaves every isolation and retention gate false; this
evidence path is now wired into the durable experiment supervisor and sealed
with runtime ACL setup in a paired artifact. Manifest, result,
supervisor-check, and
completion shapes are specified in
[`windows_appcontainer_access_probe.schema.json`](windows_appcontainer_access_probe.schema.json).
`DurableDevelopmentalLearningProtocolStore.persist_condition_worker_access_probe_completions(...)`
now seals the two condition reports together with their exact manifests and
the existing branch-preflight/profile-pair artifact identities. Reload checks
both reports, manifest-to-profile SID bindings, sentinel-check digests, and
the paired artifact digest; a report counts as a complete matrix only after a
zero exit code. Failed or incomplete checks can be retained as
evidence, but cannot be interpreted as isolation success; report authenticity
and experiment-supervisor orchestration remain separate requirements.
`DurableDevelopmentalLearningRunner.run_condition_worker_access_probe(...)`
sends one probe RPC
over each supplied supervisor-side pipe connection, derives peer expectations
from the launched process handles, waits a bounded interval for worker exit
and checks the observed status code before persisting the paired report. It rechecks live branch bindings when
the runner owns those branches and returns the immutable artifact identity
plus a false-by-default gate summary. It does not launch or terminate workers,
or infer learning; a worker that stays alive remains incomplete.
`launch_condition_worker_access_probe(...)` composes the already-bound profile
pair, AppContainer pipe launcher, endpoint acceptance, probe exchange, durable
recording, and bounded cleanup into one no-model run. Cleanup may terminate a
worker that remained live or exited with failure, but only after its completion was recorded
as incomplete; forced termination never changes that status. The supervised
run result shape is included in the access-probe schema.

[`windows_appcontainer_profile.py`](../../sentientos/windows_appcontainer_profile.py)
now provisions a per-user AppContainer profile name deterministically from
the frozen protocol ID and condition. It uses
`CreateAppContainerProfile` with zero capabilities and derives the SID for an
already-existing profile, following Microsoft's documented lifecycle. Profile
state persists after the helper returns; deletion and safe cleanup are a
separate lifecycle operation and are not implemented. Provisioning output is
identity evidence only: it does not show that the profile is safely ACLed, that
the worker can access its intended files, or that a peer is denied.
See [CreateAppContainerProfile](https://learn.microsoft.com/windows/win32/api/userenv/nf-userenv-createappcontainerprofile)
and [DeriveAppContainerSidFromAppContainerName](https://learn.microsoft.com/windows/win32/api/userenv/nf-userenv-deriveappcontainersidfromappcontainername).
The provisioning record also resolves `GetAppContainerFolderPath` and captures
its reparse-safe directory identity. `inventory_condition_appcontainer_profile_data(...)`
now produces a bounded, reparse-safe recursive inventory of regular files and
directories, binding directory and file identities plus each default-stream
content digest. It requires the captured root identity and fails closed on
reparse points, excessive depth/count/bytes, or identity changes. The returned
artifact explicitly leaves worker quiescence, snapshot atomicity, alternate
data streams, and security metadata unverified. `verify_regular_tree_inventory(...)` and
`verify_condition_appcontainer_profile_data_inventory(...)` independently
check their closed shapes, topology, root binding, and digests. Their
machine-readable shapes are specified in
[`windows_appcontainer_profile_data_inventory.schema.json`](windows_appcontainer_profile_data_inventory.schema.json)
and [`windows_custody_regular_tree.schema.json`](windows_custody_regular_tree.schema.json).
It is an observation primitive, not a complete state-boundary attestation;
profile data remains unaccounted and retention eligibility stays false until
its lifecycle is bound to the condition snapshots. The supervisor cannot
directly open the AppContainer registry store. Microsoft documents
`GetAppContainerRegistryLocation` as the API for obtaining the registry
storage associated with an AppContainer; it returns the current profile's
registry key and requires the caller to run as, or impersonate, a user who can
access that profile. Registry inventory therefore belongs inside the
SID-verified condition worker, not in supervisor code that guesses an
undocumented `HKCU` mapping path. See
[GetAppContainerRegistryLocation](https://learn.microsoft.com/windows/win32/api/userenv/nf-userenv-getappcontainerregistrylocation)
and [CreateAppContainerProfile](https://learn.microsoft.com/windows/win32/api/userenv/nf-userenv-createappcontainerprofile).
The worker opens its process token and reads `TokenIsAppContainer` /
`TokenAppContainerSid` through Advapi32, matching the documented DLLs for
[OpenProcessToken](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocesstoken)
and [GetTokenInformation](https://learn.microsoft.com/windows/win32/api/securitybaseapi/nf-securitybaseapi-gettokeninformation);
the latter returns `TOKEN_APPCONTAINER_INFORMATION` for the SID query.
The ordered worker preflight now sends the file access probe followed by a
registry-inventory request over the same process-bound pipe. The registry
response carries the complete bounded inventory, which the RPC verifier checks
against the exact request SID and both nested digests. The supervisor persists
each condition's inventory with launch PID, process-creation time, process
nonce, protocol, branch preflight, profile-pair, and probe-manifest bindings.
A paired baseline pins the first observations; later preflights may use a new
worker process only when the registry content digests remain equal. The
baseline deliberately remains an observation: writer quiescence, atomicity,
security metadata, and full profile-state accounting remain false.
`inventory_current_appcontainer_registry(...)` verifies the current process
token SID before opening the API-provided registry root, stores only typed
value digests, and enforces key, depth, value-count, and serialized-size
bounds, including a fixed 64 KiB per-value read buffer. Oversized values are
rejected without retrying at a larger allocation. Its observation schema is
[`windows_appcontainer_registry_inventory.schema.json`](windows_appcontainer_registry_inventory.schema.json);
the durable worker artifact and paired baseline are specified by
[`durable_learning_profile_registry_inventory_artifact.schema.json`](durable_learning_profile_registry_inventory_artifact.schema.json)
and [`durable_learning_profile_registry_inventory_baseline.schema.json`](durable_learning_profile_registry_inventory_baseline.schema.json).
Filesystem and registry state remain unaccounted and no retention contrast is
eligible until the complete condition state boundary and isolation policy are
verified.
`verify_condition_appcontainer_profile_pair(...)` binds the two profile records
to one protocol and requires distinct SIDs, data-root identities, and
non-overlapping paths. It is record validation only; it reports profile and
registry state as unaccounted and cannot qualify retention.
The persisted result shape is closed by
[`windows_appcontainer_profile_pair.schema.json`](windows_appcontainer_profile_pair.schema.json),
and `verify_condition_appcontainer_profile_pair_result(...)` rechecks the
pair digest and invariant false gates after reload.
`DurableDevelopmentalLearningProtocolStore` can persist and reload this pair
under the exact frozen protocol digest. The no-inference
`prepare_condition_branch_preflight(...)` returns the immutable profile-pair
artifact and protocol-bound inventory artifact references for both conditions.
Each inventory is separately reloadable and bound to the exact profile-pair
artifact and branch preflight. Capture records file-tree observations without
claiming that a worker was stopped; the artifacts keep quiescence, state
accounting, registry accounting, and retention flags false. The inventory
artifact shape is specified in
[`durable_learning_profile_data_inventory_artifact.schema.json`](durable_learning_profile_data_inventory_artifact.schema.json).
The ordered worker preflight additionally returns the paired registry
inventory baseline and its condition artifact references. This does not change
the branch-preflight schema or open an isolation gate. The pair artifact also
binds the branch-preflight ID and digest, and
reload rejects a mismatch. The store-artifact envelope is described in
[`durable_learning_condition_profile_pair_artifact.schema.json`](durable_learning_condition_profile_pair_artifact.schema.json).
The new `launch_condition_appcontainer_worker(...)` entry point composes that
profile with the suspended process launcher and records protocol, condition,
profile name, and observed token-SID match in launch evidence. If launch fails
after profile creation, the per-user profile remains. This still does not grant
runtime/state ACLs or qualify the isolation preflight.
`launch_condition_appcontainer_worker_pair(...)` can launch both workers from
the verified profile-pair record and checks each observed token SID against its
condition binding. If the second launch fails, it terminates and closes the
first worker. Pair launch evidence still reports filesystem and conversation
store isolation as false; the subsequent ordered worker preflight supplies
process-bound RPC and access-matrix evidence without promoting those gates.

[`windows_appcontainer_pipe.py`](../../sentientos/windows_appcontainer_pipe.py)
adds the first local transport primitive. It creates one message-mode pipe under
`\\.\pipe\LOCAL\`, gives the package SID read/write-data rights without pipe
instance-creation rights, rejects remote clients, and bounds each message to
1 MiB. The server accepts only the PID and process-creation time observed for
the intended worker; the client similarly checks the supervisor identity. This
provides endpoint/process binding and bounded transport only. The supervisor-side
`exchange_condition_worker_rpc(...)` adapter now binds the accepted peer PID,
creation time, and package SID to the launch observation, sends a validated
closed request, and validates the response against that launch's start nonce.
It returns response digests and correlation evidence; the registry-inventory
operation also carries the bounded typed inventory that the RPC validator
rechecks against the requested SID and its content digest.
`launch_condition_appcontainer_worker_pair_with_pipes(...)` provisions both
condition endpoints before process launch and passes pipe name, condition,
profile SID, protocol, and supervisor identity as reserved environment fields.
`bootstrap_condition_worker_pipe_from_environment(...)` checks those fields,
verifies the worker's own AppContainer SID, and binds the server to its expected
PID and creation time. The launcher records a SHA-256 digest of the exact
UTF-16 environment block, including the per-condition receipt artifact when
configured. The bootstrap can load that staged bundle only when supplied the
detached protocol and verifies its store artifact, root identity, condition,
and bundle binding before exposing it in worker context. This binds startup
configuration to launch evidence, but does not authenticate that the observed
process actually consumed the environment or establish effective ACL denial.
The dispatcher and bounded worker loop are present.
`ConditionWorkerRPCDispatcher` in
[`durable_learning_condition_worker_rpc.py`](../../sentientos/durable_learning_condition_worker_rpc.py)
requires every caller to provide an explicit per-worker operation allowlist,
routes only that subset of registered operations to a worker-local backend,
returns digest-only results for existing operations, and poisons the worker after an ambiguous backend failure
so it cannot accept another operation before restart and recovery. The worker
pipe loop is bounded and stops after that failure. Backend methods that write
must journal request IDs and recover idempotently; the production branch-owned
backend and crash/restart recovery proof are not implemented yet. These pieces
do not authenticate filesystem access or establish retention eligibility. The
RPC dispatcher has no permissive default: omitting the allowlist is a caller
error rather than enabling every registered operation. Existing baseline,
recovery, and profile-state workers each pass their own fixed allowlist. The
wire digest fields use bare lowercase SHA-256 hex, matching the experiment's
`digest_payload()` protocol, task, and artifact identities; the process-start
nonce remains a separate 32-character hex value.
`serve_condition_worker_access_probe_once(...)` now serves the ordered
`probe_access_matrix` and `inventory_profile_registry` requests, sends the
checked registry payload with the second response, closes the pipe, and returns
after both requests so the thin worker can terminate after its request sequence. Other registered
operations remain available only through the general bounded worker loop.
`python -m sentientos.durable_learning_condition_worker_entrypoint` is now the
thin pre-acquisition worker: it consumes protocol digest, condition, nonce,
AppContainer SID, and access manifest from bootstrap context, constructs a
profile-state-preflight backend/dispatcher, and serves both ordered requests. It requires no
branch/session construction or receipt bundle and has no inference path. The
launcher now binds the frozen protocol digest as a reserved environment value
alongside the protocol ID. `launch_condition_worker_access_probe(...)` also
requires an explicit map of curated runtime directories. It pins every root
identity before granting either condition SID inheritable read/execute access;
overlapping roots are rejected and any partial ACL failure prevents launch.
These ACL changes persist after the run. The setup report verifies ACE shape
and directory identity only; effective access and peer denial still come from
the worker probe and remain independent gates.
[`durable_learning_condition_worker_backend.py`](../../sentientos/durable_learning_condition_worker_backend.py)
now implements baseline inspection against a detached, verified protocol and
one worker-owned branch. It checks the baseline history snapshot, empty active
session, branch-local state/writeback/session root separation, and V10 session
inventory. The baseline report is version 2 and includes a handle-bound
inventory of every entry in the dedicated operation-journal root, including
non-JSON files and child directories. Baseline readiness requires that root to
be empty; inventory or identity failures reject the preflight. The report
shape is specified by
[`durable_learning_worker_baseline_inventory.schema.json`](durable_learning_worker_baseline_inventory.schema.json).
`serve_condition_worker_baseline_once(...)` now supplies a dedicated transport
boundary for that observation: it requires a dispatcher whose only permitted
operation is `inspect_baseline`, accepts exactly one such request, validates
the correlated response against the supervisor-observed process-start nonce,
and closes the worker pipe. It cannot continue on the same connection into a
write, score, or second inspection operation. The helper is transport plumbing
only; the current executable entrypoint still launches the profile-state
preflight worker. The baseline backend now has a closed runtime-manifest
builder and verifier, plus a factory that constructs its read-only stores from
the verified root paths and volume/file IDs. The manifest binds protocol,
condition, preregistered branch ID, AppContainer SID, session ID, and the four
disjoint roots. The builder and ACL grant path reject both overlapping resolved
paths and duplicate volume/file identities across all eight roots; its schema is
[`durable_learning_worker_baseline_runtime_manifest.schema.json`](durable_learning_worker_baseline_runtime_manifest.schema.json).
For paired v2 manifests, the builder validates each branch's private ACL using
that branch's own AppContainer SID; callers supply the peer SID with the peer
roots so the other condition's legitimate grant is not misclassified as a
broad ACL. The paired builder accepts both condition-to-root maps, SID bindings,
and session IDs, creates both reciprocal manifests, and rejects any root
identity or branch-ID mismatch observed between the two constructions. Callers
can pass that pair directly to the supervised preflight. This makes supervisor
construction and worker-side validation explicit, but
the pipe-aware launcher now accepts a verified protocol plus one verified
manifest per condition and injects those values through reserved bootstrap
environment fields. The dedicated
[`durable_learning_condition_baseline_worker_entrypoint.py`](../../sentientos/durable_learning_condition_baseline_worker_entrypoint.py)
constructs only the manifest-derived read-only stores and serves one baseline
RPC. `grant_condition_worker_baseline_read_access(...)` grants each condition
SID read/traverse access to its own four roots only; the peer roots are checked
for overlap before any grant is applied. These grants persist and remain setup
evidence, not proof of effective access or peer denial. The worker path still
provides no host isolation evidence until a live access matrix verifies those
outcomes.
`DurableDevelopmentalLearningRunner.launch_condition_worker_baseline_preflight(...)`
now composes the supervised path: it serializes worker startup, checks the
protocol/branch/profile bindings and absence of a prior paired baseline,
validates disjoint roots, grants shared runtime read/execute and
condition-local read-only data access, then launches only the baseline worker
entrypoint. It accepts both identity-bound pipes, persists the condition
reports only after each one-shot worker exits with status zero, seals the pair,
and closes all process and pipe handles. A timeout or nonzero worker exit
interrupts the run before that condition report is persisted; the interruption
record preserves a bounded failure code distinguishing the two cases. An
incomplete ACL setup returns without launching, and an
incomplete observation cannot become a ready pair. Returned ACL setup remains
diagnostic and does not claim effective enforcement or isolation. A
protocol-scoped immutable interruption artifact now records partial ACL setup,
launch phase, observed process identities, created and accepted endpoints, and
cleanup failures. It blocks retry, including when only one condition baseline
artifact was persisted. Its shape is specified by
[`durable_learning_worker_baseline_interruption.schema.json`](durable_learning_worker_baseline_interruption.schema.json).
The supervised preflight can receive either the already-verified paired
manifests or both condition root maps and session IDs. In the latter form, it
uses the persisted profile pair's AppContainer SIDs to build and verify the
reciprocal manifests itself before applying any ACL changes.
A successful launch also pins both ACL setup reports, the per-condition
manifest digests, and the complete paired v2 runtime manifests in an immutable
runtime-setup artifact before process start; the v2 paired baseline references
that artifact. Before ACL changes, the launcher checks that each manifest's
peer condition, branch ID, root paths, and root identities match the other
manifest's own roots, and that its state, history, and session roots plus
session ID match the live condition branch verified by the supervisor. Setup
artifact persistence and reload also compare each manifest session ID with the
sealed branch-preflight digest. The
setup artifact is evidence of the requested grants
and the exact roots that were supplied; its effective-access, peer-denial, and
isolation flags remain false. A setup artifact without a paired result blocks
a repeat launch as unresolved. Its shape is specified by
[`durable_learning_worker_baseline_runtime_setup.schema.json`](durable_learning_worker_baseline_runtime_setup.schema.json).
The same reciprocal-pair check runs when a setup artifact is persisted and
reloaded, so individually valid but mutually inconsistent manifests cannot
become durable setup evidence.

Protocol v12 also requires the condition worker's baseline report to include
the complete receipt-verified historical integer probe inventory. Baseline
inventory v4 carries the exact sorted inputs and inventory digest; the
supervisor reconstructs the inventory digest, binds the history snapshot, and
compares both values with the v12 protocol before accepting a completed
baseline. This closes the history-overlap check across the worker boundary.
Older protocols retain their v2/v3 report shapes. This remains model-free
preflight evidence and does not itself establish worker isolation or authorize
an inference run.

The v3 baseline inventory also carries a live, non-mutating branch-root
access matrix. From inside each worker, it opens each of its four own roots
with list/read-attributes access and compares the opened directory identity
with the pinned manifest, then attempts the corresponding peer root and records
the Win32 result. The supervisor verifies the matrix digest and binds it to
the stored paired manifests. A v3 worker response is completed only when the
matrix passes; otherwise its full inventory is retained as a rejected baseline
observation and the paired baseline cannot be ready. A matrix passes only when
all own roots open with matching identities and every peer open is denied with access denied (error
5); handles are closed and no branch files are read or modified. This is
effective access evidence for those directory opens at observation time. It
does not establish complete filesystem or process isolation, nor does it
enable scoring, writeback, or retention claims. No Windows host run has yet
validated this path.
The worker RPC now returns the closed baseline report on completed and
rejected preflights, and the supervisor-side response verifier binds its
digest to the request's expected baseline digest and checks the journal
inventory's internal digest and empty/count consistency. This is a
no-inference baseline check and does not enable journal mutation. The pipe
exchange wrapper also carries that verified response payload into its
supervisor-side exchange record; the report remains ineligible as process or
filesystem isolation evidence. `DurableDevelopmentalLearningProtocolStore`
can persist the report as an immutable condition artifact, binding its digest
to the RPC request, worker process observation, branch preflight, and paired
AppContainer profile. New v2 member artifacts also store the worker's natural
zero exit; v1 artifacts remain readable as historical evidence. Reload
verifies those bindings and the journal's internal inventory digest. The artifact schema is
[`durable_learning_worker_baseline_inventory_artifact.schema.json`](durable_learning_worker_baseline_inventory_artifact.schema.json).
`DurableDevelopmentalLearningRunner.run_condition_worker_baseline_preflight(...)`
now exchanges one no-inference baseline request with each already-launched
condition worker, requires an observed zero exit before persisting each response,
and seals the pair under one
protocol-scoped immutable artifact. The first observation may omit an
expected report digest; the worker still requires the frozen protocol history,
empty session, disjoint roots, and empty journal gates. The first pair pins
those observed digests, and a second pair for the same protocol is rejected.
Reload recomputes paired readiness from both member artifacts. The artifact
and result shapes are specified by
[`durable_learning_worker_baseline_inventory_pair.schema.json`](durable_learning_worker_baseline_inventory_pair.schema.json) and
[`durable_learning_worker_baseline_preflight.schema.json`](durable_learning_worker_baseline_preflight.schema.json).
The supervised `launch_condition_worker_baseline_preflight(...)` path now
owns process launch, one-request pipes, baseline-only owner initialization,
report persistence, and cleanup; failures are sealed as interruption evidence.
`from_worker_readonly_baseline_stores(...)` now provides a baseline-only
construction path from the condition's state, history, session, and journal
roots. It rechecks each root identity with the worker AppContainer SID, rejects
overlapping roots, reads completed history/receipt pairs through the existing
read-only store verifier, and has no model, admission writer, or writeback
operation. The dedicated baseline entrypoint receives the verified runtime
manifest through reserved bootstrap fields and serves one no-inference RPC.
This completes the baseline observation path, but does not itself exercise
developmental writeback or establish learning.
Receipt recovery now indexes only requested entries from the
worker's staged condition bundle and caches that score-free index for its
subsequent operations. `from_worker_bootstrap_context(...)` binds that backend
to the bundle, storage-artifact digest, and verification returned by the worker
pipe bootstrap; it checks protocol, condition, branch, SID, and bundle digest
bindings whenever a receipt bundle is supplied. The receipt bundle is now
optional during pre-acquisition setup, allowing baseline and access-matrix
operations before acquisition receipts exist. Receipt-recovery operations
remain unavailable without a verified staged bundle.
`from_worker_local_runtime(...)` now assembles exactly one branch from the
worker-local resident owner and session store, derives its retained-state
resolver from that experience source, and uses a rejecting invocation executor
with no serving controller. It takes no callable from the supervisor. This
supplies the backend seam without giving the worker supervisor-owned siblings
or model-serving authority. It now requires a separate identity-pinned journal
root and constructs the condition-bound journal inside the worker. Baseline
inspection includes that root in the disjoint-root inventory. The supervisor
must grant only that worker's branch-state modification ACL before launch; the
constructor does not grant access. The backend rejects tasks absent from the bundle,
does not open
the shared protocol store or peer artifacts, and never replays model calls.
It now preserves the staged store-artifact digest alongside the inner bundle
digest, includes both in the recovered receipt-index digest, and carries the
store-artifact digest into each score-free consolidation source. This binds
the resulting history snapshot to the exact staged envelope as well as the
selected entries. V2 additionally carries retained-history record refs and
experience/feedback exposure digests into each source, after verifying that
the refs reproduce the acquisition's retained-state digest. This makes the
specific past-state exposure reviewable from the eventual history record;
legacy v1 bundles remain readable but lack those refs. Each source also
retains its verified acquisition outcome ID/digest,
outcome-verification digest, and invocation-attempt ID, so later
history review can trace the prompt/response back through the supervisor's
verification record without copying score material or raw receipt text. This
is provenance linkage, not proof of custody or worker authenticity: source
invocation receipts remain marked as not reverified, and receipt custody
remains unauthenticated.

`ConversationSessionDurableLearningContext.prepare_serving_turn(...)` now
exposes the idempotently persisted user turn as a JSON-safe, digest-bound
preparation object. It carries the exact prompt, user-turn identity, correlation
ID, and caller linkage for a separate serving broker, while marking inference
and response commitment false. Its shape is specified by
[`durable_learning_serving_turn_preparation.schema.json`](durable_learning_serving_turn_preparation.schema.json).
The same module exposes `verify_durable_learning_serving_turn_preparation(...)`
to recheck the closed field set, frozen protocol/task/condition/session
bindings, prompt digest, caller correlation, and preparation digest before a
broker uses the prompt. `ProductionServingDurableLearningExecutor` now consumes
this preparation when its context resolver supports the split API, then checks
that the response recorder resolves to the same turn before invoking the
existing governed serving path. After inference returns, the executor reloads
and verifies the stored chat receipt against that session, user turn, client
request digest, prompt, output, and caller linkage before committing the
assistant turn. It then requires the persisted assistant text, model identity,
receipt references, and output-lineage object to match the verified receipt
before accepting the executor result. Resolvers without the split API retain
the legacy preparation path but still require stored-receipt verification. The
preparation verifier checks content binding only; it does not authenticate an
IPC peer or process.
This is the serializable preparation half of the worker/broker turn boundary;
response commitment still uses the in-process receipt recorder, so the
isolated serving path remains incomplete and retention eligibility stays false.

The bounded
`prepare_consolidation_snapshot` RPC now validates the complete recovered
receipt digest sequence in protocol task order against the local transcript, verifies prompt/output
linkage, checks recorded experience exposure and the unchanged protocol
baseline, and constructs a score-free World-State snapshot. It now compares
the canonical payload digest multiset before and after World-State building,
failing closed if any source payload—including retained-state references or
experience/feedback exposure metadata—was altered or omitted. Its preparation
evidence now carries the observed baseline history-state digest alongside the
match result, so the positive check is attributable to the exact state digest
read from the worker-owned branch. The supervisor-side consolidation snapshot
builder also requires the active branch transcript to contain exactly the
two uniquely identified turns (one prompt and one response) for every
preregistered acquisition task, in acquisition order; both the supervisor
projection and worker snapshot reject malformed, duplicate, unrelated, extra,
or reordered turns instead of silently ignoring them. The request must
name the complete ordered sequence of invocation receipt digests for this condition. It is
read-only:
its result marks source receipts as not reverified, custody as unauthenticated,
and developmental writeback as not performed. Snapshot identity is content
derived from the manifest, sources, and facts, so a worker restart can rebuild
the same prepared snapshot from the immutable bundle and unchanged branch
transcript without replaying model calls. This covers preparation only; any
future mutating tick still needs a durable idempotency journal and crash/restart
recovery proof. The closed `consolidate_branch` RPC now also requires the
prepared snapshot digest. Before a not-yet-started operation can proceed, the
worker checks the exact recovered acquisition-receipt digest sequence, frozen
consolidation-policy digest, and locally rebuilt snapshot digest. The request
digest therefore binds the mutation intent to the exact cognitive input
snapshot. Completed and ambiguous requests are resolved from the journal
before rebuilding state, so recovery cannot replace or replay the original
mutation. The mutation runtime remains disabled pending worker isolation and
crash/restart qualification. `ConditionWorkerOperationJournal` now provides a condition-root
intent/completion format using immutable Windows publication and reparse-safe
reads. An intent is published before side effects; an exact completed request
returns its stored result, while an intent without a completion returns an
ambiguous state that must not be replayed. Its recovery reader is wired to the
disabled consolidation operation; it does not publish new intents or execute
mutations until worker isolation and crash/restart qualification pass. A
completion retry now canonicalizes the supplied result and returns
the existing receipt only when its result digest matches; a different result
under the same request ID fails closed as a completion conflict. Version 2
completion publication now reloads the immutable file after publish and returns
the stored winner, so a losing concurrent publisher cannot report its own
different, unpersisted result as durable. Version 2
intents expose the exact prepared snapshot digest as a
separate, validated field tied to the full request digest. Version 2 completion
receipts repeat that digest and verify it against the intent, so recovered
results remain directly attributable to the cognitive input without
reconstructing the original request. It permits only one consolidation intent
in a condition journal scope. An immutable scope reservation is published
before the request intent, so concurrent different request IDs contend on one
fixed name; only the request whose digest matches the stored reservation may
proceed. Exact-request contenders then contend on the immutable intent name,
so at most one receives the new-intent status and the others see recovery
state. A different request ID after reservation is an explicit scope conflict,
preventing a second resident tick. Recovery must reuse the original request
ID. Its writer can verify the exact worker AppContainer SID against the
journal root ACL and requires a dedicated identity-pinned root. Its closed
artifact shape is specified in
[`durable_learning_condition_worker_operation_journal.schema.json`](durable_learning_condition_worker_operation_journal.schema.json).
`consolidate_branch` now reads that journal on restart: a completed request
returns its stored completion digest, an incomplete intent is rejected as
ambiguous without replay, and a different request ID is rejected after any
intent has started. A request with no intent is rejected before any intent is
written because the mutation runtime is still disabled. New worker
ticks therefore remain gated until OS isolation evidence and tick-to-journal
recovery are wired together. Projection reconstruction and probe operations
also remain rejected. See Microsoft's
[named-pipe creation](https://learn.microsoft.com/windows/win32/api/namedpipeapi/nf-namedpipeapi-createnamedpipew),
[named-pipe security](https://learn.microsoft.com/windows/win32/ipc/named-pipe-security-and-access-rights),
and [client process identity API](https://learn.microsoft.com/windows/win32/api/winbase/nf-winbase-getnamedpipeclientprocessid).

[`durable_learning_condition_receipts.py`](../../sentientos/durable_learning_condition_receipts.py)
adds the supervisor-side builder for a complete, condition-scoped acquisition
receipt bundle, now schema v2. It verifies each source outcome and invocation receipt before
projecting only task, outcome, prompt/output digest, and receipt linkage; score,
scorer attestation, and raw text are excluded. The closed bundle schema is
[`durable_learning_condition_acquisition_receipts.schema.json`](durable_learning_condition_acquisition_receipts.schema.json).
The bundle verifier checks protocol/condition/task binding and its digest, but
does not reverify source receipts or authenticate custody. The worker must not
trust a staged bundle until the supervisor pins its digest in immutable
condition-local startup evidence and the access matrix proves peer denial.
`stage_condition_scoped_acquisition_receipt_bundle(...)` now publishes it via
the handle-bound immutable Windows publisher, applies the package SID's
read-only data/traverse ACL (without file execute rights) to the pre-existing
identity-pinned, dedicated receipt root, and verifies the root contains only
that bundle before and after the grant. It verifies readback through
reparse-safe custody. The pipe-aware launcher accepts a root and artifact for
each condition, validates their protocol/condition/SID bindings, and injects
them as reserved worker bootstrap fields. The worker bootstrap reopens the
artifact through handle-bound custody against the pinned root identity. The
launch record binds the exact environment block and reports each artifact
digest. The no-model `launch_condition_worker_access_probe(...)` path now
performs a supervised live access-matrix run for the paired workers; this is
implemented code, not host acceptance evidence. It is separate from receipt
bundle consumption: authenticated consumption evidence and source-receipt
reauthentication inside the worker remain unimplemented. Until the live probe
has been completed and reviewed on the target Windows host, the worker must
not trust a staged receipt bundle. Its shape is specified in
[`durable_learning_condition_receipt_bundle_store.schema.json`](durable_learning_condition_receipt_bundle_store.schema.json).

The experimental Windows 11 `CreateProcessInSandbox` API is not the baseline
for this design: Microsoft currently labels it experimental and documents its
filesystem and capability policy as dependent on AppContainer being enabled.
It may be evaluated separately, but its presence must not be mistaken for a
supported or verified worker boundary. See [Create Process in Sandbox APIs](https://learn.microsoft.com/en-us/windows/win32/secauthz/createprocessinsandbox).

Before any model call, the platform preflight must observe the launched
process token and verify both sides of the access matrix against real branch
sentinels: each worker can read and write its own sentinel, cannot open its
peer's sentinel or supervisor scoring custody, and receives the expected
denial result. It must also verify that neither worker inherited a handle or
capability that bypasses those ACLs. A successful launch, token SID, ACL
snapshot, or self-reported denial alone is insufficient; retain the attempted
open result and require the OS error for every failed open; an unopened
sentinel cannot claim identity, content, or end-of-file verification. Successful
opens must not carry a stale error code. Until that preflight passes on the
actual host, the worker isolation and retention-eligibility fields remain
false. This is a required security acceptance run, not an inference test.

The supervised, platform-specific probe implementation now exists, but the
required target-host acceptance evidence is still absent. Local path
comparisons remain necessary, but are not substitutes for denied
cross-branch access. The persisted artifacts deliberately keep process and
filesystem isolation and retention eligibility false. The draft
[`durable_learning_host_acceptance_policy.md`](durable_learning_host_acceptance_policy.md)
defines the bounded claims a probe reviewer may accept and the further
evidence required for any future retention-eligibility review; it is not
acceptance evidence and does not authorize promotion. Until a target-host run
is reviewed and the complete state boundary is established, V10 remains
descriptive-only even when local setup checks pass.

If supervised startup fails after creating only part of the worker pair, the
interruption artifact now retains the observed process identities and the
condition endpoints created before cleanup, along with a bounded cleanup-failure
classification. This preserves partial launch evidence when the launcher
raises before returning its process and endpoint maps. The interruption still
blocks retry, and partial launch evidence cannot qualify isolation or retention.
The interruption verifier also checks that every observed worker and accepted
pipe belongs to a recorded endpoint, and that a returned launch contains both
condition endpoints. This makes the partial lifecycle internally consistent
without treating it as an isolation result.

Evaluation trajectory reporting now includes nonshared family strata as explicit acquisition-only and delayed-only rows with metric coverage counts, plus per-phase coverage for tasks without family metadata. This makes gaps in the shared-stratum comparison visible; the trajectory remains descriptive over disjoint task inputs and is not evidence of causal transfer by itself.

Evaluation v32 adds a task-level spread summary for paired answered-probe
Brier deltas: how many task pairs favor each condition, ties, and the observed
minimum, maximum, and mean. The Brier delta is available minus withheld, so a
negative value means lower observed squared probability error in the available
condition. This is a descriptive summary across recorded task pairs; it makes
no independence assumption and estimates no uncertainty. The verifier retains
an explicit v31 projection without these fields, then reconstructs v30 and
older immutable evaluation shapes through the existing compatibility chain.

The family phase-effect trajectory coverage expansion is evaluation v31. It
reports nonshared family strata and tasks lacking family metadata; the verifier
retains an explicit v30 projection that reconstructs trajectory v1 for
immutable prior evaluations.

### First-time worker-owned consolidation transaction still to implement

The existing in-process `run_branch_consolidation_ticks(...)` path in
`durable_developmental_learning_experiment.py` is the reference for the
resident tick contract. The isolated worker backend builds and digest-binds
the score-free acquisition snapshot and can reconcile an already completed
owner tick into its worker journal. When the condition tick has not started,
`consolidate_branch(...)` still rejects the new operation without reserving an
intent. Do not enable the RPC by calling the existing two-branch runner from a
worker: that runner owns both branches and would cross the worker boundary
this design is establishing.

The worker implementation must be a per-condition transaction. It must
validate the exact prepared snapshot, frozen consolidation policy, and
condition's preregistered history exposure; publish the worker operation
intent before invoking `owner.run_tick(...)`; and pass no scorer outcomes or
attestations into the owner. For the withheld condition, the invocation must
retain the existing no-history observation requirements. The available
condition may receive only its preregistered target experience record refs.
After the tick, the worker must reload tick status, cognition observations,
history state, writeback record, and writeback receipt, then verify them
against both the immutable worker intent and the original baseline before
publishing journal completion.

The first-time mutation path remains disabled. A completed bounded access
review is not enough to enable it: that review establishes only the observed
sentinel access results for one run. Before any worker can publish a new
developmental-history record, a separately reviewed process and state boundary
must establish that no inherited handle, broker path, recovery action, or
unaccounted persistent state can cross conditions. Until that broader boundary
is machine-checked and bound into a new protocol, the recovery owner remains
constructed with `enabled=False`, its invoker rejects model calls, and
`consolidate_branch` may only reconcile an already completed owner tick.

The versioned v1 boundary-acceptance artifact and source-reloading verifier
are implemented in `durable_learning_boundary_acceptance.py`; the experiment
store can persist, reload, and revalidate their source artifacts. The
contract binds the exact protocol and worker executable, both condition
process identities and launch configuration, inherited-handle and
broker-capability inventories, condition-local filesystem, registry, profile,
service, recovery, and history state, scorer custody, and reviewer
disposition. Its verifier rejects missing or asymmetric inventories and keeps
the bounded access-matrix result as cited but insufficient evidence. It fixes
process and filesystem isolation, retention eligibility, and worker mutation
eligibility to false. No target-host boundary artifact has been accepted.

The remaining gate work is to produce complete target-host inventories and a
separate review, then integrate an accepted artifact into protocol-specific
eligibility. That integration must reopen the evidence and match the exact
protocol digest, worker pair, host build, and condition pair; changes require
a new artifact and protocol. It must derive `worker_mutation_eligible` from
the verified boundary artifact plus preregistration and baseline evidence,
never from a caller-supplied boolean. It must not promote the bounded
sentinel review or alter the fixed process-isolation, filesystem-isolation,
and retention-eligibility claims. Until accepted evidence and this gate
integration exist, `worker_consolidation_execution_not_enabled` remains the
required result for a not-started tick.

Restart reconciliation must compare the owner tick ID, snapshot ID and digest,
condition history policy, typed observation, append-only history delta, and
reloaded writeback receipt with the original intent. A verified completed tick
may be committed to the operation journal without invoking the owner again.
An interrupted owner tick, a changed snapshot, incomplete observation, or
unattributed history change must remain ambiguous and reject replay. The
current resident tick journal and the worker RPC journal are separate stores;
the bridge must explicitly prove their cross-store recovery behavior rather
than assuming that either one covers the other's crash window.

Read-only snapshot preparation now returns the baseline history-state digest
and exact record ID/digest refs, the complete source fact ID sequence, the
available arm's preregistered history refs (empty for withheld), and the
history-withholding posture. The closed `consolidate_branch` request binds
those values alongside the acquisition receipt sequence, policy digest, and
snapshot digest. The worker checks them against its own reconstructed snapshot
before reaching the still-disabled execution gate. This gives the restart
reconciler the baseline needed to distinguish the intended append from later
or unrelated history changes; it does not enable a tick.

Worker operation intent v3 now stores the complete validated consolidation RPC
payload, not only its digest. Reload revalidates the closed RPC payload and
recomputes the original request digest from the immutable intent. Thus the
baseline refs and history policy remain available after supervisor restart for
cross-store reconciliation of a completed owner tick. The intent still has no
execution or isolation authority, and the worker continues to reject first-time
mutations.
The journal reader retains v2 intent/completion compatibility: verified v2
completions remain readable, while a v2 intent without completion remains
ambiguous and cannot receive a new completion under the v3 contract. When a
current request retries an older request ID, the reader reconstructs the v2
request digest from the three fields that existed in the v2 payload, then
checks those values against the current request before returning a stored
completion. This preserves exact-request recovery without treating the newly
added baseline fields as if they had been part of the historical intent.

This software sequence remains non-executable for retention claims until the
paired target-host access matrix has passed the reviewed isolation policy.
Implementing the transaction does not promote process isolation,
filesystem isolation, or retention eligibility, and does not establish that
the model used the retained strategy or improved on held-out probes.

### Worker journal to resident tick recovery slice

`consolidate_branch(...)` now handles worker/owner recovery without replaying
cognition. For a pending worker intent, it reconstructs the frozen acquisition
snapshot and checks its digest, then asks the resident owner for the
deterministic condition tick's persisted status. With no worker intent, it
also recognizes an already completed owner tick under that exact identity;
after verifying it, the worker creates and completes the recovery journal
entry. Only an already completed tick can proceed. The worker reloads the
typed condition observation and current history state, verifies the expected
history exposure and snapshot binding, enforces append-only baseline record
identity, and checks that any new writeback record and receipt match the
resident tick and selected source facts. It then seals a score-free recovery
result in the worker journal. On later journal replay, it requires acquisition
receipt recovery, rebuilds the snapshot, reloads the owner tick and observation,
and requires the newly reconstructed recovery result to match the sealed
completion before returning it. A missing owner recovery API, not-started or
interrupted tick, malformed observation, changed owner state, or unattributed
history delta remains ambiguous and is rejected without replay.

The new-operation path checks for a preexisting owner tick only through
`developmental_tick_status_readonly(...)`. It no longer falls back to
`developmental_tick_status(...)`, whose owner recovery behavior may reconcile
writeback state while reading. If the pinned read-only API is missing or fails,
the worker rejects before creating a journal intent; recovery inspection must
not cause a writeback side effect. The returned checkpoint must also have the
exact `{status, tick, authority}` shape, `authority: false`, a recognized
status, and either no tick for `not_started` or a tick row whose ID matches the
requested condition tick. Malformed or cross-tick status evidence is rejected
before reconciliation.

The worker now also catches unexpected ordinary exceptions from journal
inspection, score-free snapshot reconstruction, and completed-tick
reconciliation at the RPC boundary. It returns a bounded machine reason (or a
fixed fallback) rather than propagating exception text or terminating the
worker request path. These catches do not convert partial recovery into
success: the result remains rejected, with no authority or developmental
writeback claim. The code change has not yet been exercised by worker-runtime
evidence.

This implements reconciliation of an already completed owner tick only. It
does not run a first-time resident tick: when the deterministic owner tick is
not started, new operations still return
`worker_consolidation_execution_not_enabled` without reserving a journal scope.
The original baseline-only environment entrypoint still allows only
`inspect_baseline` and constructs a read-only owner. The separate
`from_worker_local_runtime(...)` factory also disables inference. A later,
recovery-specific environment entrypoint now constructs the receipt-backed
owner and exposes `consolidate_branch` only for reconciliation of an already
completed tick; it does not enable first-time cognition execution. The paired
target-host access-matrix acceptance evidence is still absent. The draft
[`durable_learning_host_acceptance_policy.md`](durable_learning_host_acceptance_policy.md)
defines a review standard but has not been applied to a host run. Consequently
this recovery path does not qualify isolation, retention contrast, learning,
or probe use; it can only reconcile state if a separately authorized owner
tick has already completed.

To reduce the runtime's dependency on an active model, the resident cognition
owner now accepts an optional `invocation_receipt_verifier` separate from its
inference `invoker`. Persisted observations still require the exact receipt
verifier contract; this change only allows a receipt-store adapter to reload
past cognition without loading a model. The default continues to use the
invoker as verifier for existing runtimes. At that point in the design
sequence, the worker bootstrap had not yet provided a condition-local
persisted-receipt verifier. The later recovery bootstrap now supplies one
backed by staged invocation receipts; receipt reads remain allowlisted,
condition-scoped, and separate from inference.

The earlier baseline worker context did not contain enough custody information
to construct that adapter safely: its `condition_receipt_store_artifact`
described the staged acquisition bundle, not the governed model-invocation
receipt directory. Its bundle-custody and source-reverification fields remain
false and must not be treated as invocation-receipt custody. The later recovery
path addresses this with a separate condition-local invocation-receipt store
artifact; the acquisition bundle still cannot stand in for that store.

The reusable model-free adapter and condition-local store staging/reload
primitives now exist in `sentientos/durable_learning_invocation_receipts.py`.
Staging re-verifies the exact source receipt refs, removes optional output text,
publishes immutable `lmrec-*.json` entries in a dedicated root, grants only the
condition AppContainer receipt-read access, and returns a closed artifact
with root identity and the exact receipt ID/digest allowlist. Reload checks the
artifact and every receipt through handle-custody reads before constructing a
verifier. At runtime, the verifier reads only requested allowlisted entries,
rejects duplicate keys and non-JSON constants, calls the existing
`validate_receipt`, and checks the observation's request ID/digest, active model
identity, and resident serving-session binding. The artifact format is
specified in `durable_learning_condition_invocation_receipt_store.schema.json`.
The AppContainer process launcher can now pass the staged root and artifact to
the worker bootstrap pipe. The pipe reloads and verifies the store and places
the model-free verifier in `worker_context`; `from_worker_local_runtime(...)`
injects it into the worker-created resident owner before constructing the
branch. This does not create or invoke a model.

`DurableDevelopmentalLearningRunner.prepare_condition_worker_recovery_inputs(...)`
now performs the supervisor-side evidence preparation. It reloads and
reverifies the persisted acquisition outcomes, gathers each branch's verified
observation receipt refs, stages the score-free acquisition bundle and exact
invocation receipt allowlist under that condition's AppContainer SID, and
builds a reciprocal pair of pinned branch runtime manifests. It rejects
conflicting receipt identities and any overlap between branch roots and staged
receipt roots. It persists and reloads a content-addressed recovery-input
artifact that binds the staged receipt stores, profile-pair artifact, ACL
reports, root paths, receipt counts, and reciprocal runtime manifests. The
artifact is specified in
`durable_learning_condition_recovery_inputs_artifact.schema.json`.

This preparation step does not grant branch journal write access or launch the
recovery entrypoint. If preparation stops after one condition has been staged,
that condition's immutable root and read ACL may remain; operators must treat
it as partial setup rather than a completed recovery run. The worker side still
fails closed when a receipt is absent from the staged allowlist or its root
identity changes, and the receipt verifier cannot reach a supervisor, peer
branch, or inference backend.

Recovery ACL setup is now distinct from the baseline read-only grant:
`grant_condition_worker_recovery_access(...)` grants each worker read access
to its own state, history, and session roots, with modify access confined to
its dedicated operation journal. The runner's
`prepare_condition_worker_recovery_setup(...)` also grants the declared runtime
roots and persists/reloads a recovery setup artifact that binds those grants
to the recovery-input and profile-pair artifacts. The setup artifact is
specified in `durable_learning_condition_recovery_setup_artifact.schema.json`.
It retains false effective-access and peer-denial claims. The recovery worker's successful
`prepare_consolidation_snapshot` RPC can return a bounded, schema-checked
score-free evidence projection so a supervisor can form the final
`consolidate_branch` request. The projection is bound to protocol and
condition, and explicitly carries no score material, receipt reauthentication,
developmental writeback, or authority claim. This closes an RPC data-flow gap;
it does not execute a recovery worker or establish developmental learning.
`DurableDevelopmentalLearningRunner.launch_condition_worker_recovery(...)`
now consumes the complete persisted setup, writes a retry-blocking launch
intent before starting processes, pins the recovery entrypoint through the
existing launcher, binds each launched executable's observed digest to the
prelaunch intent, and runs the versioned RPC sequence in order for both
conditions. Policy-bearing protocols add projection reconstruction after
consolidation; the run records its complete result beside the earlier request
and response digests, worker identities, cleanup state, and terminal outcome.
An unresolved intent blocks automatic relaunch after an interrupted process;
the v1 schemas are `durable_learning_condition_recovery_intent.schema.json`
and `durable_learning_condition_recovery_run.schema.json`, while the extended
sequence uses `durable_learning_condition_recovery_intent_v2.schema.json` and
`durable_learning_condition_recovery_run_v2.schema.json`.

Both persistence and reload validation enforce RPC progression: a worker cannot
issue a later recovery operation after an earlier operation was rejected or
failed. An interrupted attempt may retain the last request with an unknown
response, but that row must be the final observed operation. The
`reconciliation_not_available` status is accepted only when earlier operations
completed and a terminal reconciliation was rejected; a generic worker failure
cannot be recorded as an unavailable reconciliation. Persisted launch evidence
is also checked against each saved full process-observation digest and the
prelaunch executable digest map. Its condition SIDs and profile identities,
environment hashes, staged receipt bundle digests, and runtime-manifest digests
must match the persisted profile-pair and recovery-input artifacts. Isolation
and RPC-dispatch claims remain explicitly false. The run schema constrains the
launch record's shape and its non-authority flags.

Completed baseline-inspection and snapshot exchanges must retain their result
objects in the run artifact, with each object matching the response digest.
Baseline inspection also retains its result for an explicit rejection; a
failed inspection and any non-completed snapshot must carry no result object.
This prevents a status and digest from standing in for evidence that the
supervisor actually consumed.

Terminal run statuses also require a recorded worker-pair launch, full process
observations for both conditions, and all four RPC attempts per condition.
The JSON Schema pins the four request operations by array position and requires
each observed exchange to repeat its request's operation; runtime validation
also matches request IDs, condition, and process identity.
When launch itself fails before returning pair evidence, only an interrupted
`worker_pair_launch` record with no RPC attempts is valid; any partial process
identities remain explicitly partial. This prevents a caller from persisting a
terminal outcome from fabricated RPC rows without the launched workers that
would have produced them.

The run status `completed` means the bounded worker sequence completed. A
`reconciliation_not_available` result means the worker could not reconcile an
already completed owner tick. Neither status establishes new developmental
learning: inference, scoring, writeback, and learning claims remain false in
the run artifact. The persisted recovery-input artifact continues to record
`worker_launched: false` and `journal_write_access_granted: false`; it is
preparation evidence, while the separate run artifact records launch results.
The worker side now fails closed when a receipt is absent from the staged
allowlist or its root identity changes, and the receipt verifier cannot reach
a supervisor, peer branch, or inference backend. Persisted-observation
recovery now has a dedicated `durable_learning_condition_recovery_worker_entrypoint`.
It constructs the real resident owner with `enabled=False` and a receipt-only
invoker, validates checkpoint status with the new no-repair
`developmental_tick_status_readonly(...)` API, and exposes only baseline
inspection, acquisition receipt recovery, consolidation snapshot preparation,
and completed-tick reconciliation. The ordinary baseline entrypoint remains
read-only and inspection-only. The supervisor now stages each condition's
invocation receipts referenced by recovered cognition observations and
acquisition outcomes, binds them to a dedicated receipt-store artifact, and
launches this recovery entrypoint through the paired AppContainer worker
runner. The four RPCs inspect the baseline, recover acquisition receipts,
prepare the score-free snapshot, and attempt completed-tick reconciliation.
That last operation can only commit an owner tick that already completed; a
new tick remains disabled. The end-to-end supervisor path is implemented but
has not yet been exercised in a production experiment run. The reviewed
target-host access-matrix acceptance evidence is still absent. The draft
[`durable_learning_host_acceptance_policy.md`](durable_learning_host_acceptance_policy.md)
does not change that status: worker launch evidence does not establish process
or filesystem isolation and does not qualify a retention contrast.

### Read-only owner tick reconciliation guard (2026-11-23)

A source audit found that completed-tick reconciliation could fall back from
`developmental_tick_status_readonly(...)` to the legacy
`developmental_tick_status(...)` API. That legacy API may repair checkpoint
state while loading it, which is incompatible with crash reconciliation's
read-only claim. The worker now rejects recovery when the no-repair API is
unavailable; it never uses the mutating fallback. This tightens recovery
evidence integrity only. It does not enable first-time consolidation, process
isolation, or developmental writeback, and it has not been exercised in a
worker run.

The reconciliation boundary now independently requires the read-only
checkpoint response to contain exactly `status`, `tick`, and `authority`, with
`authority` false and status `completed`. This check also covers recovery from
an already persisted worker journal, where the earlier preflight check is not
repeated. It rejects malformed or authority-bearing status objects before
observation and writeback lineage can be reconciled.

### Versioned boundary-acceptance evidence contract

The separate boundary-acceptance contract is now represented by
`durable_learning_boundary_acceptance:v1` and
`durable_learning_boundary_acceptance.schema.json`. Its verifier reloads every
referenced content-addressed source and binds the exact persisted protocol,
protocol-declared condition pair, worker executable digests, host build,
process identities, and launch-configuration digests. It requires complete,
classified inventories for inherited handles and broker capabilities and for
each condition's filesystem, registry, profile, service, recovery, and history
state. History inventories must share the protocol's baseline-history digest;
the available branch may contain only the exact preregistered experience
digests, while the withheld branch must contain none. Each branch also reports
its exact history delta digest list, which the verifier checks against that
preregistered set and the inventory's `preregistered_experience` entries.
Both history inventories must enumerate the same sorted baseline record-digest
set under the protocol's baseline-state digest. The other persistent-state
categories must match across the condition pair.
The paired state inventories must use matching scope digests; recovery
inventories must show no unresolved intent or cross-condition recovery
reference. The protocol-specific bounded access review is retained as a cited
input, but is insufficient on its own. Scorer custody and a distinct
independent-review disposition are also bound into the artifact.
Reviewer identity and independence are operator-supplied declarations, not
cryptographically authenticated; the artifact fixes both authentication claims
to false, so a digest proves record integrity but not who performed the review.

This contract is currently an evidence verifier and inventory entry only. No
worker-executable, process-boundary, handle, broker, or complete persistent-
state inventories have been accepted on the target host, and no boundary
acceptance artifact exists. The artifact fixes
`worker_mutation_eligible`, process/filesystem isolation, retention eligibility,
learning, and authority to false in every disposition. The worker therefore
remains disabled for first-time consolidation. Before any future protocol can
reference accepted boundary evidence, persistence must reopen each source and
match the protocol digest, worker pair, host build, and branch pair; the
separate protocol-gate integration and independent target-host review remain
required.
The recovery worker now also supports `reconstruct_strategy_projection` after
it reloads a previously completed owner tick. The returned projection remains
non-consumable: the worker marks its supplied consolidation-receipt reference
and answer-exclusion audit as unverified, and fixes
`answer_example_exclusion_verified` and `probe_use_eligible` to false. This
does not enable first-time writeback, delayed probes, or retention eligibility;
the independent auditor must still verify the reconstructed projection before
any prompt can receive it.

Recovery intent/run v1 remains immutable and pins exactly four operations,
ending with `consolidate_branch`. Policy-bearing protocols now use intent/run
v2, which adds a fifth `reconstruct_strategy_projection_v2` operation and
persists its complete response. The run verifier binds that response to the
protocol, condition, policy digest, request/result digest, and launched worker
process. Protocols without a strategy-projection policy continue to use the
four-operation v1 sequence. A v2 run records reconstruction evidence; it does
not prove caller-held receipt or audit artifacts were verified. Those claims
and probe eligibility remain false until independently bound by the
experiment's persisted consolidation receipt and answer-exclusion attestation.

The worker RPC now also has `reconstruct_strategy_projection_v2`. Its request
contains only the protocol-bound strategy-projection policy digest; it no
longer accepts caller-supplied consolidation-receipt or audit digests that the
worker cannot verify. Its result reports the policy digest and reconstructed
projection plus the reloaded owner-tick completion and its digest. The runner
checks that the completion is protocol, condition, branch, tick, and snapshot
bound to the projection before exposing both as recovery evidence. This retains
the observation and writeback lineage needed for later receipt reconstruction.
The result keeps supervisor-evidence eligibility, audit verification,
probe use, adoption, and authority false. The legacy v1 operation remains
available for compatibility. The v2 supervisor run persists the new result
without upgrading it to probe-eligible learning evidence.
The runner's `load_recovered_strategy_projection(...)` handoff reloads that
v2 run and verifies the projection against the current condition branch before
returning its run, response, and worker-process references. For protocols that
preregister an independent exclusion auditor, the runner can bind the supplied
auditor attestation to that recovered projection and persist it through the
existing signed-attestation verifier. The returned audit record still fixes
probe use, adoption, and authority to false; normal delayed-probe gates retain
their separate consolidation and evidence requirements.
The persisted gate-evidence response uses schema v6 for the new boundary
acceptance collection, leaving historical v4/v5 schemas unchanged. The
collection reports reviewed artifacts and fixed-false eligibility claims only.
