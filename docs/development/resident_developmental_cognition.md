# Resident developmental cognition composition

Resident cognition may receive a separately keyed `prior_self_model` only under
explicit longitudinal runtime configuration. It is never merged into
`current_evidence` or `developmental_history`. The daemon runs cognition before
same-tick reconciliation, and receipts bind the exact earlier projection and its
claim/source identities. Current evidence controls current-condition reasoning;
prior representation may be useful, stale, contradicted, incomplete, or
irrelevant. Neither substrate grants authority.

The optional [developmental cognitive-model replacement experiment](developmental_model_replacement_experiment.md) consumes frozen read-only projections and separately governed endpoints. It is not part of resident cadence and cannot mutate activation, serving, history, or canonical explicit-user retention.

This surface is an explicitly configured, bounded bridge in the real
`sentientosd` maintenance cadence. It does **not** close the broader
developmental organism and does not activate the legacy dream, curiosity,
goal-curation, self-narrative, value-drift, or inner-world loops.

## Configuration and cadence

`SENTIENTOS_RESIDENT_DEVELOPMENTAL_COGNITION_CONFIG` names a JSON file using
the exact v1, v2, or v3 configuration shape. V1 retains the original enabled
posture, separate history and composition-state roots, allowed World-State
source kinds, fact/retrieval bounds, and opt-in paired comparison. V2 adds the
separate model-replacement artifact root. V3 adds
`max_inference_timeout_seconds`, bounded from 1 to 120 seconds; older
configurations preserve the 30-second default. This setting bounds each
governed cognition invocation, including controlled-history conditions and
objective protocol probes. It does not authorize additional calls or change the
separate per-session call count and workload gates. An absent or disabled
configuration performs no developmental model call, admission issuance, or
write. Unknown, malformed, contradictory, or unusable configuration degrades
only this surface and records the reason.

`sentientosd` retains the exact validated in-memory `WorldStateSnapshot` that
it writes for the tick. Immediately after building that board, it calls the
owner once with the same object and tick ID. The JSON board artifact is never
used to reconstruct authority, and existing board feedback is unchanged.

## Deterministic selection and temporal boundary

Selection filters facts by the exact configured source-kind allowlist, orders
them by source kind, source ID, and fact ID, and takes at most the configured
count. A digest-sealed, atomically replaced state records exact per-fact
selection identities and completed ticks, so identical evidence is not
reinterpreted after restart. This is structural deduplication, not forgetting,
motivation, importance scoring, preference, identity, or reward.

At the beginning of tick N, the owner reconstructs a bounded recent projection
only from records named by earlier completed ticks. It captures that projection
before interpreting or writing tick N. Therefore a record written on tick N is
ineligible for tick-N cognition and becomes eligible no earlier than a distinct
later tick. Reconstruction from the same roots proves process-reconstruction
continuity, not universal crash recovery.

## Authority and cognition boundaries

The existing `ResidentDevelopmentalWritebackController` still validates the
selection, performs governed interpretation, constructs the typed candidate,
verifies admission, appends immutable history, and writes the durable receipt.
A separate `RuntimeAdmissionAuthority` issues an exact candidate-bound,
operation-bound, configuration-digest-bound, one-sequence admission only after
the candidate exists. The model and World-State cannot choose admission fields.

Later-tick cognition uses an exact bounded current-evidence projection containing
fact payloads, source provenance, and applicable conflicts, rather than snapshot
identifiers alone. It uses the local governed purpose
`resident_developmental_retrieval_cognition`. Its durable observation binds the
model/artifact, request and receipt, current snapshot and projection identities,
exact current fact IDs, tick/correlation, and
exact retrieved record IDs/digests without retaining the raw prompt. It is an
observation only: no effect, goal, policy, authority, action, self-model, or
canonical memory mutation follows.

When `comparison_enabled` is true and prior history exists, a protocol is
persisted before three fixed-order calls: history present, history withheld by
projection only, and exact history restored after durable re-read and digest
verification. Existing `measure_changed_cognition()` reports only observable
output-digest differences and restoration stability. Difference is not improvement,
correctness, learning, sentience, selfhood, or consciousness. Comparison is
off by default.

### Fresh companion consequence-store setup

The local companion runner can be configured for a first operator-confirmed
embodied consequence cycle before any consequence chain exists. Use the v5
World-State projection schema with `enabled: true`, an explicit `store_root`,
empty evidence-selection lists, and `live_consequence_store_enabled: true`.
This mode creates the dedicated consequence store for writes while returning
no prior consequence facts to cognition. It does not discover or import history;
later reads still require an explicit projection configuration selecting
verified chain IDs. Earlier projection schemas retain their nonempty-selection
requirements.

### Request-scoped companion interaction

The owner also exposes an opt-in run_companion_interaction boundary for a
caller that already holds a validated in-memory World-State snapshot. It
retrieves only completed developmental history, accepts separately keyed
self-model and epistemic projections, and invokes the same governed
resident_developmental_retrieval_cognition purpose. The model must return a
bounded decision with exact citations to current fact IDs; unbound answers are
rejected. This path does not run the developmental writeback transaction or
mark an interaction tick complete. Invocation receipts and cognition
observations retain identities and digests, not raw prompt, screen text, user
question, or response text. The response is returned to the caller in memory
for immediate delivery. The chat service commits the assistant turn with the
observation, inference receipt, and response digests, then verifies those bindings
on idempotent recovery instead of invoking cognition a second time. This stored
reply remains distinct from developmental-history writeback.

### Semantic history beyond the per-query sample

The embedding runtime is opt-in. Run `python -m pip install ".[semantic-history]"`
with Python 3.10+ to provide the CPU sentence-embedding package. This extra is
excluded from the base and `full` installs because it brings the PyTorch runtime.
The model itself
must already be present in the local Hugging Face cache at the configured
immutable revision. Retrieval pins loading and encoding to CPU and does not
download a model; if the package or cached revision is unavailable, selection
uses the explicit lexical fallback policy.

When an immutable-revision CPU sentence embedder is configured, each query still
embeds at most 256 records: the newest 192 and up to 64 older lexical/stratified
candidates. Successfully embedded records also enter an immutable derived vector
cache under the cognition-state root. Each entry binds the exact durable history
record digest, the digest of the text projection supplied to the embedder, the
embedder identity, the tick when it was first indexed, and the vector digest; it
stores no history text. A later tick may rank all matching cached vectors, up to
the 4,096-record history bound, while current-tick additions remain unavailable
to same-tick ranking. The v18 retrieval policy identity binds the embedder and
the exact cached/current vector inputs used for selection. Decision polarity
ranks first, then lexical relevance, then semantic similarity. Thus an
above-floor semantic-only record can still outrank the recency fallback when
no lexical match exists, while it cannot displace a lexically relevant record.
A semantic score below 0.25 is excluded; the policy version binds both this
fixed cosine floor and the ranking order. Cache custody or validation failure
does not discard the current bounded semantic batch, and an unavailable or
malformed embedder still selects under the explicit lexical fallback policy.
The floor is a software default, not a claim that every embedder has equivalent
similarity calibration.

`tests/test_resident_developmental_cognition.py::test_weak_semantic_matches_do_not_displace_lexical_or_recent_history`
checks that a sub-floor match falls back to recency and that an above-floor
near-match cannot displace exact lexical relevance. Strong lexically disjoint
retrieval is covered by
`test_semantic_history_retrieval_recovers_lexically_disjoint_experience`.
`tests/test_resident_developmental_cognition.py::test_indexed_semantic_history_changes_later_fake_decision_across_restart`
uses deterministic vectors to place a lexically disjoint old record in one
tick's bounded sample, then demonstrates that a fresh owner can retrieve and
apply it on a later tick even when it is absent from that tick's embedding
batch. Withholding removes the decision effect; restoring the history and
reopening the owner restores it. This is a synthetic retrieval/application
counterfactual. It does not establish real embedding quality, real-model
adherence, generalized learning, or improved decisions.

An explicitly operator-confirmed companion developmental cycle can also use a
configured longitudinal self-model owner. The bridge captures the eligible
prior self-model and epistemic projections after constructing the cycle's
validated World-State snapshot and before cognition. Bounded selected snapshot
facts provide relevance terms for those prior projections; the facts remain in
their separate current-evidence channel and do not alter prior posture. The
bridge then runs the existing governed
interpretation/writeback owner, then reconciles the same bounded World-State
snapshot through that existing self-model owner. The reconciliation uses the
snapshot's timestamp boundary rather than the request's opaque cycle ID. As in
the daemon cadence, that same-cycle reconciliation cannot enter the cognition
that preceded it; only a later cognitive tick can select it. The cycle response
reports reconciliation status and identity separately from developmental
writeback, including a degraded status if reconciliation fails after writeback.
This does not roll back or misreport an already committed writeback.
The deterministic integration test
`tests/test_resident_developmental_cognition.py::test_confirmed_developmental_cycle_uses_current_observation_to_retrieve_prior_epistemic_state`
demonstrates a current observation selecting the matching prior position in the
production cycle path. This proves selection and prompt delivery under a fake
invoker; it does not establish that a real model applies the position
appropriately.

On Windows, longitudinal self-model reconciliations now use the existing
handle-bound immutable publisher when the configured custody root already
exists and passes the private ACL check. A directory-identity-bound local
mutex serializes reconciliation generations across processes, and restart
recovery verifies the resulting immutable chain.

The developmental-history store now also publishes immutable learning records
and writeback receipts on Windows when its configured root exists with a
verified private ACL. Records and receipts use the existing handle-bound,
no-replace publisher, and the writeback operation lock is scoped to the verified
root identity. A deterministic native test writes both artifacts, acquires the
lock, reconstructs the store, and verifies their record/receipt linkage after
restart. This enables durable history storage on Windows; the resident owner
also persists its mutable composition checkpoint with atomic replacement and
serializes ticks through a state-root-identity-bound local mutex. Runtime
admission ledger updates use the same private-root discipline, and cognition
observations are durably published and recovered from their own private child
directory. Exact-name reads now tolerate bounded sibling entries in shared
state roots while still enforcing the selected-file count and byte limits.

A native Windows integration test exercises two ordinary `run_tick` calls from
separate owner instances. The first tick admits and retains a lesson; the second
reconstructs checkpoint, observation, admission, record, and receipt custody
after restart, selects the earlier record, and changes a deterministic fake
invoker's interpretation only when that history appears in its prompt. This
demonstrates the integrated software path with a controlled substitute; it does
not demonstrate real-model learning or improved real-world decisions. A second
native Windows integration test now persists and reloads the controlled A/B/A
history comparison protocol and outcome run. It verifies that the deterministic
fake's present and restored outcomes differ from withheld history and match one
another; the result remains a bounded observed association, not a learning or
causal claim. Objective-task plans and score checkpoints now use the same
private Windows state-root custody policy and recover with the run after owner
restart. A deterministic objective-transfer fixture demonstrates that scored
history-present and restored answers are correct while the withheld answer is
not; this is a controlled software result, not evidence of real-model learning
or generalization. No GPU or real-model validation was performed.

A renderer's proprioceptive report remains a report from the renderer, not an
independent measurement of the avatar's actual effect. The self-model owner
preserves that provenance and uncertainty; these claims are read-only,
non-authoritative, and do not establish action, consequence, learning, or
improved performance. This bridge connection is opt-in and does not reconfigure
a running companion.

The local companion launcher keeps ordinary serving and controlled comparison
in separate `ResidentDevelopmentalCognitionOwner` instances when
`comparison_enabled` is explicitly enabled. The serving owner is always
constructed with comparison disabled; the comparison owner shares the exact
history root, state root, writeback controller, and governed model invoker, and
is used only by the local, operator-confirmed history-intervention endpoint.
Both owners use the resident composition lock and one durable store, so this
split does not create another memory or admission system. Without the explicit
flag, the comparison owner is not constructed and the UI does not offer that
experiment.

A saved resident-cognition reply may expose an explicit **Compare history impact
(4 inference calls)** control when the existing comparison owner is configured and the
workload gate permits cognition. After operator confirmation, the local-only
endpoint verifies the saved reply, captures one fresh consented screen observation,
and calls the existing history-present / history-withheld / history-restored owner
with the original bounded question and one matched World-State snapshot. A
request-driven screen capture is correlated to a one-time capture request; its age is
bounded monotonically from before authenticated request dispatch through
observation receipt, so bridge-send delay is included and Windows/WSL wall-clock
comparisons are avoided. The World-State snapshot retains the
capture request ID, bridge message provenance, process and consent digests, and OCR
or vision status. The cognition bridge does not independently reauthenticate the
bridge message, so evidence remains qualified as a bounded local capture. Fallback
caller-provided timestamps must be within 60 seconds and no more than 5 seconds in
the future. Raw frames are not retained. The result reports response-text stability
and measurement identity, not performance improvement.
The three comparison conditions run after the normal developmental interpretation,
so the experiment may make up to four local inference calls. It remains unavailable
during a gaming workload. It grants no action authority and is not automatically run
during chat.

The local development companion runner can opt in to this owner-level bridge
with `--enable-resident-cognition`. It requires an explicit resident-cognition
configuration, automatic foreground-game workload detection, and the supervised
Windows observer edge. The bridge reuses the companion's governed local model
invoker and the same resident history and state roots. Ordinary chat does not
write developmental history automatically. The **Learn from current scene
(governed writeback)** control appears beside a verified resident-cognition
reply as before. It now also appears beside a screen-bound `model_generated`
reply only after the stored invocation receipt verifies against the session,
source user turn, client request digest, exact transcript text, and saved output
lineage. The ordinary reply is an anchor for an explicit cycle, not evidence for
the developmental interpretation. The operator must confirm before the cycle
requests a fresh consented observation. It serializes the request with
conversation work and invokes the existing owner's ordinary `run_tick` and
governed developmental-writeback controller. It creates no additional memory
store or admission authority. The result distinguishes a retained record and
receipt from a completed tick with no eligible lesson. For a receipt-verified
ordinary reply, any operator report remains a separate
`operator_assertion_unverified` World-State report bound to the assistant
response digest and both screen-capture digests. For an ordinary
`model_generated` reply, the report also carries the assistant turn's validated
developmental-history exposure: selection posture, selection digest, and the
bounded record IDs and digests presented with that reply, or the recorded
reason no history was selected. This binds later feedback to the context that
was available at the time; it does not establish that the model relied on that
context, that the report is accurate, or that development occurred. It has no
conversation correction target and cannot claim epistemic-state authority.
The report also cites the exact source user turn and assistant reply by turn ID
and text digest, so later cognition can recover the exchange being discussed.
These report-context citations do not imply that the earlier answer cited or
relied on those turns, and they do not validate the report. The owner must
already allow `operator_input`; otherwise feedback remains unavailable. The
immediate interpretation treats a report as an assertion rather than direct
observation and preserves conflict with scoped sensor or owner evidence.

On a later resident-cognition turn, history selection can retrieve those exact
dialogue citations from the feedback-linked session. The bridge rechecks each
turn's text digest and binds the excerpt to the feedback record, its digest, and
the session snapshot before adding it as historical cited dialogue. The prompt
labels the excerpt as dialogue rather than current evidence, and separate
reports citing the same turn are not counted as corroboration. This lets later
cognition compare the report with the actual exchange while retaining
uncertainty about the report's truth and the earlier model's reliance.

When a verified resident-cognition reply has capture lineage, the operator may
also enter a bounded correction when `operator_input` is explicitly included
in the resident cognition owner's `allowed_source_kinds`. If that reply cited
prior conversation turns, the UI lets the operator optionally bind a correction
to one cited turn. The report carries that turn ID and exact text digest, and
later history context prioritizes the targeted excerpt when it is available.
General observations may remain untargeted. The target identifies the
operator's intended referent; it does not establish the dialogue or correction
as true. Cognition compares the cited turn with a correction only when that
exact dialogue text is available. When they conflict, the prompt directs
cognition to surface the disagreement
and preserve uncertainty instead of automatically accepting either source. The
report is not independent sensor
evidence or proof that an action occurred. The UI asks for explicit confirmation
before capture and writeback. Repeating the same request identity cannot reuse
a completed tick. No gameplay action is authorized by this control. Cognition inference is
serialized against model-profile changes and unavailable during gaming workload
mode. The option remains off by default and does not reconfigure a running
companion.

This integration is not evidence of learning. Demonstrating development still
requires the full sequence of a real observation, prediction or decision, an
action, an independently observed consequence, a governed update, and a later
decision comparison with history present and withheld under controlled
conditions.
The embodied strategy scorer evaluates proposed decisions against admitted
consequence history; it does not observe an action. Its
`repeats_previously_contradicted_action` field is derived from the proposal's
`retry_prior_strategy` self-report and must not be read as an executed-action
finding. The single-consequence scorer also emits a separately named
`proposal_to_prior_command_comparison`: it compares exact proposed pose and
expression fields with the retained command record when those fields overlap,
and reports matching or differing fields by digest. Its execution posture is
`not_observed_by_this_comparison`; it does not establish that the prior command
was executed or that the new proposal was acted on. Both single- and multi-event
comparisons now reject proposals from different situations or body generations,
so the history conditions remain anchored to one frozen decision context.

### One explicitly staged objective intervention

The ordinary daemon configuration never receives a persistent objective task.
For a single same-model history experiment, an operator may stage one bounded
request in the configured cognition `state_root`:

```sh
python scripts/stage_resident_objective_intervention.py \
  --request-id history-transfer-20261013-01 \
  --multiplier 3 --offset 2 \
  --probe 7 --probe 8 --probe 9
```

The command uses `SENTIENTOS_RESIDENT_DEVELOPMENTAL_COGNITION_CONFIG` (or an
explicit `--config`) and only writes
`pending_objective_intervention.json` under that configuration's state root.
Before writing, it read-only verifies that a completed cognition checkpoint
names at least one record whose writeback admission and receipt still verify;
uncheckpointed or interrupted record publication is not treated as eligible,
and staging is refused when no such history exists. The check never repairs
composition or history custody. Its output says `staged_not_authorized`: it
does not load a model, admit a call, or grant serving authority. On the next
operator-triggered run with an exact World-State snapshot, the configured
resident owner reads the request through bounded custody. Windows staging and
recovery require an existing private state root; a state-root-bound named mutex
serializes staging with resident ticks, and request replacement and archival use
the Windows handle publisher. If eligible prior developmental history exists, the
owner binds the request and its public descriptor into a durable objective
plan before the three existing governed inference calls. If no prior history
exists, it records a terminal blocked request without inference. The request
identity is persisted with the tick, so an interrupted or completed trial is
never replayed; the staged file remains as custody evidence. An exact restage
is idempotent, while replacing the occupied slot with different bytes is
rejected until its identity is terminal. Before staging a different request,
the prior request bytes are published into a separate immutable archive under a
bounded 1,024-file limit; a new request ID cannot reuse an identity already in
the durable tick ledger. A later experiment therefore requires a new request ID
and separately reviewed history/context.

The experiment tick produces scored experiment custody only. It does not create
a developmental-history writeback, update canonical explicit-user memory, alter
the recurring owner configuration, or activate/replace serving. Per-call
inference admission and the resident cognition quiescence gate remain in force.
Choose a task only when its examples are already present in the retained history
available to the present/restored conditions and are absent from other current
context; the staging command does not manufacture training examples or certify
that scientific-contamination check. The answer oracle remains private to the
durable plan and is not included in the model's task descriptor. This handoff
makes the existing trial path callable; it does not demonstrate actual model
acquisition or performance. New objective run records and the result inspector
carry a task- and current-projection-bound `not_assessed` contamination posture;
the intervention owner does not claim that historical examples or answers are
absent from other context. Older runs without that field are reported as legacy
with no recorded contamination assessment.

After a completed request, daemon feedback includes a bounded score summary
reloaded through the existing run verifier and the configured invocation-receipt
verifier. It contains receipt/output digests, per-condition score status and
correctness, plus a separate `actual_nonsynthetic_inference_verified` flag; it
does not include prompts, output text, or the oracle. After restart, a fully
checkpointed interrupted trial can be reconstructed and summarized without
repeating inference. Missing or unbound receipts leave the actual-inference
flag false, and failure to render this optional summary does not change the
already completed trial result. For each condition it also compares the
receipt-bound effective `max_new_tokens` ceiling with the preregistered request
budget and reports output-byte truncation. A reduced ceiling is visible in the
result; there is no independent verification of a natural-stop reason, so this
summary does not claim that the model used the entire budget or stopped before
the token ceiling. When the llama.cpp response includes its own completion
reason and token usage, the governed v3 invocation receipt retains those
bounded backend-reported values. A reported `length` finish is treated as
truncated and cannot produce a valid objective score; the receipt binds this
report but does not make the backend an independent observer. Older receipts
and backends without completion metadata retain an explicit unavailable posture.

An operator can retrieve the same result after the transient daemon feedback is
gone, using the exact request ID and digest printed by staging:

```sh
python scripts/inspect_resident_objective_result.py \
  --config <resident-cognition-config.json> \
  --serving-config <resident-model-serving-config.json> \
  --request-id <staged-request-id> \
  --request-digest <staged-request-digest>
```

This command reads the sealed cognition tick ledger, the active or archived
request, the immutable scored run, and the explicitly configured installation's
serving and inference receipts through a read-only installation view. It never
constructs a serving controller, loads a model, admits inference, repairs
custody, or writes a new experiment. It returns an incomplete/unavailable status
when a scored run or required receipt cannot be verified; it does not replay an
interrupted request. The report separates score validity from actual governed
inference verification and omits raw prompts, outputs, and oracle data.

Progression output keeps the requested `max_output_chars` limit separate from
receipt-reported output bytes. It carries allocation, attempt, and consumption
receipt identities only as invocation-receipt linkage until the resource ledger
is independently reconciled. CPU, GPU, energy, and generated-token measurements
remain unknown when this result path has no corroborating measurement owner.

Resource-aware task-family recommendations compare the exact
`history_present`/`history_withheld`/`history_restored` score and resource joins.
They require a distinct verified inference receipt for each condition and
distinct measured-consumption receipt IDs and digests across all conditions;
repeated receipts make the comparison incomparable instead of counting the
same cost more than once. The full-suite correctness threshold comes from the
salted preregistered task descriptor, and a score's observed coverage cannot
lower it. Timezone-aware per-receipt event times are preserved into the later
history projection and recommendation when supplied by the ledger; malformed
times make the comparison incomparable, while legacy receipts without event
times remain explicitly undated. For the current ledger chain, the sole
`reconciled` receipt must point to the exact inference receipt and its one
`measured_*` predecessor; both rows are retained, but only the reconciled row
contributes cost. A legacy multi-row set without state cannot be counted and
becomes incomparable. Among options meeting the frozen correctness requirement,
the bounded evaluator ranks higher correct-probe count first, then lower measured
`call_units_consumed`. It never infers shared-host CPU/GPU use, or treats
expenditure as a reward or authority signal.
The strategy/model invocation-resource join also checks the exact ledger chain:
the invocation-linked measured and reconciled rows must be unique, the owner
projection must retain their `attempt_begun` predecessor, both predecessor
digests and the inference effect digest must link in order, and the reconciled
measurement must equal the measured row. Each projected receipt is also checked
against the resource owner's closed receipt schema and digest before admission.
Incomplete or substituted chains stay degraded and are withheld from verified
resource evidence; malformed receipt collections cannot abort later cognition
projection.
In cognition prompts, the three condition names are explicitly described as
experimental history-exposure labels, not current-task directives. A surfaced
recommendation remains tentative, task-family-scoped retrospective evidence;
it does not establish learning, improvement, transfer, causal benefit, or
resource savings. `call_units_consumed` is identified as ledger-reported
invocation cost and not host compute, energy, or cognition quality.
The current objective intervention invokes each of its three history-exposure
conditions once, and the governed ledger records backend entry as one call unit
per attempt. A completed three-condition run therefore cannot demonstrate
resource savings between conditions. Ledger receipt validation requires
`call_units_consumed` to equal one when `generation_attempted` is true and zero
when it is false; inconsistent measurements cannot enter later resource
recommendations. If a unique correctness score selects a
condition, that is a quality result; cost selection is demonstrated only when
owner-reconciled call counts vary between correctness-equivalent alternatives.
Synthetic fixtures that vary costs establish evaluator ordering only. Actual
resource-allocation learning needs preregistered task-strategy alternatives
with variable measured call counts and independent held-out quality scoring.
The recommendation artifact also types its role as a historical condition
comparison, marks the selected value as a history-exposure condition rather
than a task strategy, and limits the claim to the exact task family. It also
records `selection_reason`: either a unique highest correctness score selected
the condition, or measured cost broke a tie between equally correct
conditions. Prompt projection re-verification requires and preserves these
semantic fields.
This semantic contract is `sentientos.resource_strategy_recommendation:v3`;
older v1/v2 recommendations remain historical data but are not admitted into
later prompts as verified recommendations because they lack the typed selection
rationale.
Before task-family history reaches a later cognition prompt, the recommendation
digest and full-suite requirement are checked and the recommendation is rebuilt
from the retained three-condition score and ledger evidence. A mismatch removes
the recommendation from the prompt and records a rejected-reverification
posture; it does not suppress the underlying historical evidence.

Before staging, an operator can run a bounded read-only preflight against one
explicitly selected model file:

```sh
python scripts/doctor_resident_objective_experiment.py \
  --config <resident-cognition-config.json> \
  --serving-config <resident-model-serving-config.json> \
  --model-path <operator-selected-model.gguf> \
  --allowed-root <narrow-authorized-model-root>
```

The doctor validates the bounded developmental-history records, candidate
lineage, exact writeback receipts, and recorded runtime admissions through the
existing writeback recovery verifier in read-only mode. It never creates an
admission authority or repairs a missing receipt; an interrupted
record/receipt publication is reported as unavailable until the normal
cognition recovery path reconciles it. If a concurrent writer publishes while
the inspection runs, the bounded snapshot may be reported incomplete and can
be inspected again. This check confirms recovery eligibility at inspection
time, not that a later task will retrieve the record. It also checks the
selected artifact through
`local_model_commissioning.inspect_artifact`; it never searches model roots.
It also reports the current Python executable/version, operating-system and
architecture identifiers, whether the `llama_cpp` package is discoverable, and
whether the process exposes the POSIX descriptor, no-follow, fsync, and flock
primitives used by existing custody owners. The WSL field is only a host-marker
observation. GPU offload, filesystem crash durability, daemon identity, serving,
and inference admission remain explicitly unobserved; a listed primitive does
not prove that a particular mount implements the required durability.
When an explicit serving configuration is supplied, the doctor resolves its
installation identity through `InstallationStateRegistry.open_read_only` and
checks that exact installation root without constructing a serving controller
or scanning alternate roots. `ready_for_operator_review` means only that these
preflight observations passed. If the explicit serving configuration is
omitted or its installation root is unavailable, the doctor returns an
actionable blocked finding rather than suggesting staging is ready. Its JSON
identifies the configured history and cognition-state roots separately from the
exact installation identity/state root, and supplies a bounded
`next_operator_actions` list. These paths are configuration observations; they
do not prove that the running daemon loaded the same configuration or that the
filesystem roots share an authenticated process lifetime. The report keeps
that process/configuration binding in `unobserved_runtime_gates`; the final
operator action requires checking the daemon's actual configured environment
before staging.
The report always sets `trial_execution_ready` false because this separate
process cannot observe the daemon's World-State tick, its actual loaded model
identity, task-specific history/current-context contamination, or the effective
generation budget, and it requests no `LOCAL_MODEL_INFERENCE` admission. It
does not check the separate v3 two-model commissioning and serving gates. A
127-byte Git LFS pointer is reported as
`git_lfs_pointer_not_model_payload`; this says nothing about artifacts on another
host. The existing `scripts/local_model_commissioning.py doctor` is a legacy
discernment-calibration doctor, not an experiment readiness assertion; its
calibration fields now remain false until a process-real load verifies the exact
active identity.

#### Acquiring the first retained record

The staged history-intervention request is deliberately not a history-seeding
operation. With no eligible prior record it terminates without scoring and does
not write developmental history. The existing way to acquire a first record is
an ordinary configured resident-cognition tick: after a real source owner has
published a fact to the same tick's World-State, `ResidentDevelopmentalCognitionOwner`
selects only unprocessed facts from configured `allowed_source_kinds`, obtains
one bounded interpretation through the governed local invoker, and passes the
candidate through the existing writeback admission and durable-history owner.
The candidate and admission receipt are separate from the source event; neither
turns the interpretation into current truth, policy, authority, or a measured
task outcome. A later completed tick may retrieve the retained record.

For an acquisition-and-transfer study, the World-State fact must already carry
the actual earlier task or consequence and its independently observed outcome.
For the bounded affine task-family experiment, the history-present score row
also carries its verified score schema, evaluator identifier, plan/task digests,
and invocation output digest; each example references that score digest. This
identifies the deterministic benchmark measurement, not an external event, and
does not publish the private answer oracle.
Later task-family retrieval independently reconstructs the examples from the
score's ordered probe results, requires distinct integer probe inputs, and
checks the score's correct, answered, and abstained counts. A matching digest
label alone cannot turn altered examples into future mapping guidance.
When a task-family run is translated into evidence for epistemic-state
revision, the present and restored arms must match on each probe's correctness
and abstention outcome before a score delta can support or contradict the
proposition. A restoration mismatch is retained as contextual evidence. This
keeps a non-reproduced condition difference from becoming a directional belief
update while preserving the measured result for later review. A malformed
answer has no probe-level signature, so it also remains contextual rather than
supporting or contradicting the proposition.
Family-suite v4 selective results remain eligible for that probe-level
comparison when all three arms have complete, coherent correctness, answered,
and abstained counts; an undefined aggregate binary-correctness value alone
does not discard verified per-probe evidence.
The repository does not expose a generic command that can manufacture such an
event; use its real source owner. If no suitable source fact is present or its
kind is not configured, no initial record is produced. Do not stage the
three-condition objective request to seed history or hand-edit the history
store. The bounded history-present/withheld/restored experiment starts only
after the first record and its source and writeback custody have been
independently inspected.

#### Exact operator handoff

Run these commands from the same supported POSIX installation that owns the
daemon's cognition state and serving receipts. Replace each placeholder with
the exact configured file/root and operator-selected model path:

```sh
python scripts/doctor_resident_objective_experiment.py \
  --config <resident-cognition-config.json> \
  --serving-config <resident-model-serving-config.json> \
  --model-path <selected-model.gguf> \
  --allowed-root <narrow-model-root> \
  --task-family-id <source-backed-family>

python scripts/stage_resident_objective_intervention.py \
  --config <resident-cognition-config.json> \
  --request-id <unique-request-id> \
  --multiplier <operator-selected-integer> --offset <operator-selected-integer> \
  --probe <held-out-integer> [--probe <additional-held-out-integer> ...] \
  --task-family-id <source-backed-family> --require-task-family-history

python scripts/inspect_resident_objective_result.py \
  --config <resident-cognition-config.json> \
  --serving-config <resident-model-serving-config.json> \
  --request-id <staged-request-id> --request-digest <printed-request-digest>
```

Only `ready_for_operator_review` permits an operator to consider staging; the
doctor deliberately never reports execution-ready because it cannot inspect the
daemon's live tick, loaded identity, task contamination, effective generation
parameters, or inference admission. Staging reports `staged_not_authorized` and
waits for the already configured daemon's next ordinary tick. That owner still
requires eligible retained history and all existing serving and per-call
inference gates. Retain the request ID/digest from the staging output, then
inspect the terminal result with those exact values. The inspector itself
reports `model_invoked: false` and `write_performed: false`; repeated reads of
the same request return the same measurement digest and cannot replay inference.
The result's separate inference flag describes only whether the three
historical invocation receipts independently reconcile to completed
nonsynthetic local-model inference.

When `--task-family-id` is supplied, the doctor uses the same read-only
completed-tick and verified-writeback selector as staging and reports the
matching admitted record IDs and digests. A generic valid history record no
longer makes a family-specific preflight appear ready. This is still a custody
check, not a claim that the selected observation is true, useful, or learned.

For a transfer task that must consume a matching admitted source outcome, pass
both `--task-family-id` and `--require-task-family-history`. The family is an
operator-declared protocol label, not evidence by itself; staging checks that a
completed tick and verified writeback receipt name a retained record containing
that exact family observation. Omitting both flags preserves the historical
general-history behavior. Supplying a family without the requirement influences
retrieval when a matching record exists but does not block if it is absent.

Windows staging now uses private ACL checks and the native handle publisher;
it fails closed if those custody checks are unavailable. WSL is only a
candidate supported host when both the daemon and all three commands run inside
that same POSIX installation and share its exact custody roots. No
cross-environment request copying or Windows/WSL handoff has been verified here.
Model-serving activation and each inference
remain subject to their existing independent authorization and custody paths;
these commands create no grants.

Every projection and observation declares historical context to be read-only,
non-authoritative, non-policy, non-current-truth, and outside canonical explicit
user retention. Developmental history uses a physically separate configured
root and does not widen canonical retention semantics.

Explicit retained-memory corrections are now represented as immutable links from
a newly retained user statement to up to eight previously retained memory IDs.
The request must name those IDs; each target is checked against its source turn,
retention receipt, and exact stored-record digest. The correction bindings are
included in request idempotency and durable turn/record provenance. Retrieval
omits linked older statements from ordinary personalization, while explicit
historical-recall queries can still retrieve them. The cognition context carries
the relation as unverified user history: it does not establish objective truth
or currentness. Deterministic fake-model tests cover the storage and selection
counterfactual; real-model application and long-term behavioral improvement
remain unverified.

When resident cognition receives one of these verified links, its prompt now
uses the linked later statement as the user's updated preference when that
preference directly applies, and cites the correcting memory. The older linked
statement remains historical; the relation does not establish truth,
currentness, instruction, or authority. Unrelated unresolved conflicts still
require clarification. A restart-spanning production-path counterfactual
compares corrected preference retrieval with the same unlinked conflicting
statements using a deterministic responder. This verifies context integration
and citation lineage, not real-model adherence or improved decisions.

## Fourth substrate: prior epistemic state

Cognition can receive a separately typed, prior-tick epistemic projection binding exact proposition IDs, state IDs/digests, generations, and evidence-set digests. Current World-State evidence outranks a conflicting stale position for current-condition reasoning. Same-tick projections fail closed, so a cognition cannot certify its own update. See [persistent epistemic state](../architecture/persistent_epistemic_state.md).

Large current World-State evidence may use a typed bounded prompt projection while
remaining bound to the exact source projection digest. Every selected fact ID,
source freshness, and typed report value remains represented. When selected facts
conflict, the compact view preserves each complete conflict row and all member
fact IDs so context pressure cannot turn a contradiction into a one-sided report.
Unknown fact schemas or conflict rows remain in full form instead of being
silently summarized. This compaction changes prompt size only; it does not
resolve a conflict, establish current truth, or grant authority.

When the inference input cannot carry every complete semantic packet, selection
prioritizes proposition terms matching the current question before epistemic
severity and stable identity. Matching also preserves typed identifiers such as
`facility-1` and `exact-window-1`; discarding numeric suffixes can otherwise
make distinct propositions look equally relevant. Omitted packet identities and
digests remain bound in the observation. A deterministic budget counterfactual
checks that the matching complete packet is selected while an unrelated query
retains the established severity ordering.

Current resident cognition observations use schema V12. The V10 selection manifest preserves the self-model claims chosen for the bounded inference prompt. It binds selected and omitted claim identities to the source projection digest, appears in the inference request's upstream evidence, and is checked against the recovered observation. V11 adds companion response citations for selected self-model claims. V12 adds companion citations to exact prior conversation turn IDs. The selected turn IDs and text digests remain bound to the source snapshot and context selection digest, and recovery checks each cited digest against that selected set. Older V9 through V11 observations retain their historical field shapes and remain recoverable. These records show which context was supplied and cited; they do not establish that a model used it correctly or that it improved a decision.

The companion's committed-response verifier accepts V8 through V12 observations. For V9 and later, it checks memory citations and the memory selection digest against the durable observation. V11 also records prior self-model citations: the model may cite only selected claims in the prompt allowlist, and recovery and transcript verification bind those citations back to the recorded selection. V12 applies the same lineage check to cited conversation turns and their exact text digests. Self-model and conversation citations identify earlier context; they do not establish current truth or verified capability.

Resident-companion chat now passes up to 16 prior turns from the current
conversation snapshot, capped at 4,000 text characters. Each turn carries its
text digest and a digest of its existing linkage; the selected set has its own
digest and remains bound to the source conversation snapshot. The cognition
prompt treats this separate `session_conversation_context` as untrusted,
historical dialogue: assistant statements are not verified facts, and transcript
text is neither current evidence nor canonical retained memory. The invocation
receipt binds the exact prompt and upstream context; the assistant transcript
linkage records the snapshot digest, selection digest, and supplied turn IDs.
This enables same-session follow-up resolution without copying ordinary
conversation text into developmental history or canonical memory. A controlled
counterfactual test demonstrates that an earlier sensor statement is available
to the resident route when included and absent when withheld. It uses a test
double and does not establish real-model accuracy or improved decisions.

When an admitted operator correction cites a prior assistant response, the
service may carry its cited epistemic state IDs into the next cognition request
only after verifying the durable response linkage. These IDs remain bounded
retrieval priorities: the bridge resolves them to proposition priorities without
changing epistemic stance, evidence bindings, or execution authority.
Unverified linkage contributes no priority. CPU-only counterfactual tests show
the verified handoff reaches the bridge and the production bridge selects the
cited proposition over an unrelated state; they do not establish that a real
model will apply the selected state correctly.


History selection for ordinary cognition ticks now also considers bounded
selected current World-State facts as ranking context, except in objective,
family, intervention, and epistemic-revision paths. Companion retrieval adds
those facts only for elliptical questions, alongside the previous user turn.
The context affects which historical packets are selected; current evidence
remains separate and history remains non-authoritative. A CPU-only deterministic
counterfactual shows a matching older experience reaching the real companion
prompt and changing the fake invoker's decision over a recent unrelated record.
Real-model use of that context and longitudinal decision improvement remain
unverified.

The long-running daemon cognition path applies the same bounded selected
World-State context when ranking prior self-model claims and epistemic states.
It does so after the same-tick snapshot exists and before cognition, while
staged objective requests and comparison cycles retain their experiment-specific
projection selection. The selected observations stay in current evidence; the
retrieved projections remain historical and non-authoritative. A deterministic
daemon-path counterfactual shows a battery-overheating observation selecting
the matching prior epistemic position over a newer unrelated telescope
position, with the selected packet digest reaching the production cognition
prompt and the epistemic owner state unchanged. A paired old-ordering control
uses the same current evidence but selects the unrelated telescope position;
the CPU fake invoker then gives a different recommendation and higher
uncertainty. This demonstrates current-context retrieval changing a later
daemon cognition result while preserving the evidence boundary. It does not
establish real-model application or improved outcomes.

Elliptical companion history selection also uses bounded text from the selected,
source-turn-verified canonical user memories. When a selected memory correction
marks an older memory as superseded, only the correcting memory contributes
ranking terms; the bound memory prompt still preserves both records and their
correction lineage. These terms only rank developmental history and do not
become evidence or authority. A deterministic counterfactual shows a retained
garden constraint selecting a matching older experience over a recent unrelated
record, while a specific telescope question stays question-driven. The
experiment uses a fake invoker and does not establish real-model adherence or
improved outcomes.

In the chat path, canonical-memory source receipts are checked before the
retrieval candidate cap. If the memory directory contains more than the normal
1,024-record bound, this verified path scans at most 4,096 entries and 16 MiB,
then keeps at most the 1,024 newest source-verified records for relevance
selection. Invalid records therefore cannot consume the ordinary record bound
and hide a verified match. Generic retrieval without source verification keeps
the original 1,024-record bound, and directories exceeding the scan or byte
limits still fail closed. A CPU fixture with 1,024 invalid decoys and one
verified target demonstrates this bounded behavior; it does not establish
real-model use or decision improvement.

Source-session receipt verification is also bounded per retrieval: at most four
distinct source sessions are loaded, each through the existing 8 MiB session-file
limit, for a maximum reserved read budget of 32 MiB and no more than four cached
session payloads. Repeated records from a cached source session do not spend another
reservation. Candidates beyond that bound are recorded as deferred and omitted as
unverified; they are not labeled invalid or allowed to affect selection. A CPU-only
counterfactual checks this distinction. The bound is a conservative reservation
based on each file's maximum size, not a measure of actual bytes read. Real-model
application remains untested.

The ordinary `PersistentConversationService` prompt path now uses the same source
receipt verifier before canonical memories enter a normal chat prompt. Exact
transcript recall and check-ins that intentionally suppress memory do not scan
retained records. For other requests, records with invalid or deferred source
verification are omitted before the four-record selection cap, and the ordinary
prompt's retrieval status reports partial verification. A deterministic fake
invoker counterfactual places four newer, altered records ahead of one valid
retained statement: raw lexical retrieval selects the altered records, while the
interactive chat path supplies only the receipt-verified statement and the fake
decision changes accordingly. This establishes source-governed context assembly
for both ordinary chat and resident cognition; it does not establish real-model
interpretation, current truth, or improved outcomes. Direct low-level
`CanonicalMemoryStore.retrieve` calls without a validator remain unverified
retrieval results and must not be treated as prompt-safe evidence.

Ordinary chat also forwards the existing resident bridge's pinned semantic
memory configuration to this same verified retrieval path. When lexical
coverage is weak, bounded semantic selection can recover a paraphrased retained
statement; receipt validation still filters records before semantic candidate
selection. If the configuration is absent or the encoder is unavailable,
retrieval keeps its existing lexical behavior and exposes the fallback posture.
`tests/test_persistent_governed_conversation.py::test_ordinary_chat_semantic_retrieval_applies_only_verified_paraphrased_memory`
uses deterministic vectors to show a paraphrased older memory displacing a
newer weak lexical match in ordinary chat, verifies the unavailable-encoder
fallback, and rejects a tampered source record. This demonstrates the software
path with controlled substitutes; it does not measure real embedding quality,
real-model interpretation, or improved outcomes.

Ordinary chat now uses the existing bounded exchange-aware selector for
same-session dialogue when no narrower recall, check-in, self-contained, or
runtime-context policy applies. Relevant complete exchanges are considered
before recent dialogue fills the configured character budget, with at most 64
candidate turns. The deterministic
`tests/test_persistent_governed_conversation.py::test_ordinary_chat_uses_relevant_older_exchange_before_recent_fill`
counterfactual shows recent-only reconstruction omitting an earlier decision,
then ordinary chat selecting that source-linked exchange and changing a fake
decision while preserving the same budget. This is controlled retrieval and
application evidence; real-model interpretation remains unverified.

When resident cognition cannot handle a turn, ordinary chat can now consume an
already-enabled epistemic projection through the same complete-packet binder
used by resident cognition. The bridge applies the question relevance bound,
temporal freshness review, omission accounting, and source-bound packet format;
ordinary chat omits this context when epistemic consumption is disabled, on
narrow recall/check-in/runtime requests, or in the compact gaming prompt. The
projection is historical, non-authoritative, read-only context and does not
activate calibration review or revise epistemic state. The CPU counterfactual
in `tests/test_persistent_governed_conversation.py::test_ordinary_fallback_applies_bounded_prior_epistemic_context`
shows the supplied position changing a fake ordinary-chat decision.
`::test_bridge_binds_only_verified_prior_epistemic_context` checks that the
existing verified packet reaches this adapter and leaves admitted state
unchanged; `::test_local_chat_prompt_rejects_epistemic_context_with_authority_flags`
checks prompt assembly rejects self-authorizing flags. Real-model application
and improved longitudinal outcomes remain unverified.

When an ordinary fallback includes the projection, its selection digest is
also carried in the governed invocation linkage and saved assistant-turn
linkage. This gives later review a durable identity for the prior packet that
was presented alongside that response, without claiming that the model relied
on it. Responses without a selected packet do not receive this field. The
ordinary fallback counterfactual checks that the digest matches in both
places and is absent when no projection is selected.

For sparse ordinary fallback questions, epistemic packet ranking also receives
the latest digest-verified prior user topic from the already selected session
history. Short acknowledgments and turns with invalid text digests do not
replace that cue; specific questions remain unchanged. The deterministic
`tests/test_persistent_governed_conversation.py::test_ordinary_fallback_applies_bounded_prior_epistemic_context`
counterfactual shows the same sparse follow-up receiving the west-sensor prior
only when that topic exists in history. The portable
`::test_sparse_ordinary_epistemic_query_uses_only_latest_verified_topic` checks
the digest and acknowledgment filters. This demonstrates query construction
and prompt application with controlled substitutes; it does not establish
real-model interpretation or improved outcomes.

When the latest prior user turn is itself sparse or elliptical, ordinary
epistemic ranking also includes its immediately preceding assistant question
when that turn's text digest verifies and it contains a question mark. The
assistant text is only a topic cue;
it is not treated as evidence or authority, and invalid assistant digests are
ignored. `tests/test_persistent_governed_conversation.py::test_sparse_ordinary_epistemic_query_resolves_elliptical_answer_antecedent`
shows a verified question plus "That one" selecting the west-sensor prior while
the answer alone does not, and confirms a tampered antecedent is excluded. The
real-owner counterfactual in
`tests/test_resident_developmental_cognition.py::test_sparse_session_topic_changes_real_prior_epistemic_projection_selection`
also confirms the resolved query changes selection among persisted epistemic
propositions.

The ordinary fallback budgets this optional epistemic projection against the
complete chat prompt. It reserves framing space when asking the shared packet
binder to select prior state, then checks the serialized prompt against the
governed 8,000-character limit before keeping the projection. If there is not
enough room, the projection is omitted so it cannot make an otherwise
admissible ordinary prompt oversized. The CPU test
`tests/test_persistent_governed_conversation.py::test_ordinary_epistemic_context_uses_only_remaining_prompt_budget`
checks that a bounded prior packet remains available under the total prompt
limit, while `::test_ordinary_epistemic_context_is_skipped_without_prompt_headroom`
checks the no-headroom boundary. This establishes prompt-budget compatibility
with a controlled bridge; real-model interpretation and improved outcomes
remain unverified.

Ordinary fallback can also receive bounded developmental history through the
existing resident owner. The owner performs the existing durable-record
verification and question-relevance ranking, then emits compact packets bound
to exact record and digest identities. This ordinary-chat path deliberately
uses lexical retrieval only, so it does not invoke a configured semantic
embedding model; insufficient prompt headroom, disabled ownership, or an empty
verified projection leaves the prompt unchanged. Context assembly checks the
selection and packet identities and rejects authority flags or tampering. The
packet is historical experience, not current evidence, policy, an instruction,
or permission to update any state. Selected identities and the selection digest
are saved on the invocation and assistant turn. The model-aware owner entry
point receives the active serving identity, allowing scored task-family
examples to carry exact same-model, different-model, or unbound applicability
posture. Missing identity remains explicitly unbound and does not disable
history retrieval. This describes provenance and does not imply successful
transfer. The prompt treats these relations as applicability metadata, not
performance evidence. The provider also accepts an optional bounded record
allowlist and matching record-digest allowlist for controlled callers. The
owner revalidates that every requested record is in completed history and that
each reloaded digest matches before projecting it. The returned selection
identifies the allowlist policy and any records omitted for prompt budget, so a
future ordinary-chat intervention can verify that present and restored
conditions used the same exact content. The CPU-only
`verify_ordinary_chat_history_projection_triplet` helper validates both
projection digests, the available/selected/omitted record partition, its
prompt-budget omission digest and reason, and confirms the withheld context is
absent. Its result explicitly leaves effect and learning unestablished.
`build_ordinary_chat_history_intervention_prompts` assembles the three prompts
from one fixed context argument set, verifies present and restored prompts are
identical, and checks that removing only the developmental-history block from
the present prompt yields the withheld prompt. It binds digests for each full
prompt, the shared non-history prompt, and the exact inserted history block,
along with the intended condition order in
`sentientos.ordinary_chat_history_intervention_prompts:v3`, including one
digest that binds the prompt digests and verification metadata. An explicit trial
index cycles through all six condition permutations, placing each condition in
each position twice per six-trial block. This deterministic schedule is
counterbalancing, not randomization. Previously prepared bundles retain their
original alternating-first, restoration-third schedule and remain auditable.
The durable runner persists and assigns trial indices across trials.
`verify_ordinary_chat_history_intervention_prompt_bundle`
revalidates the prompt and schedule bindings after handoff. The bundle returns
prompt digests, not model outputs. This is prompt-control preparation, not yet
an inference runner or scored result. The deterministic
`tests/test_persistent_governed_conversation.py::test_ordinary_fallback_applies_verified_developmental_history`
counterfactual demonstrates a changed fake fallback answer when the relevant
verified history is present, and the paired prompt test checks tampering is
rejected. This proves the software path and its controlled decision effect;
real-model use, beneficial transfer, and long-term outcome improvement remain
unverified.

`build_ordinary_chat_history_intervention_protocol` now creates a digest-bound
pre-registration object from that bundle. It binds the source session and turns,
prior response digest, serving-model identity, generation-configuration digest,
task commitment, independent scoring-plan digest, and counterbalanced trial
index. Its verifier rechecks the prompt bundle and keeps authority, effect, and
learning claims false. `OrdinaryChatHistoryInterventionStore` publishes and
reloads this object immutably under the existing custody-checked experiment
protocol store. The governed chat adapter and condition runner now consume the
protocol, though no live experiment has used them.

The result-side contract is now available through
`build_ordinary_chat_history_intervention_result` and
`OrdinaryChatHistoryInterventionStore.persist_result/load_result`. A result
packet binds all three condition prompt digests to output digests, invocation
receipt references, and blinded score artifact references, and binds the packet
back to the exact protocol and prompt bundle. The packet is immutable in the
experiment run collection. The store reloads and verifies every referenced
score artifact's digest and output/plan binding. Result reload accepts the same
optional owner-backed receipt verifier used at persistence; without that
callback, receipt references are not independently reverified. Evaluation and
cohort persistence/reload forward this optional verifier, so a cohort can
recheck every invocation receipt when its verification owner is available. New
result persistence requires a receipt verifier and publishes one immutable
per-protocol finalization index bound to the execution claim and result digest;
a competing result packet cannot replace the finalized result. Finalization
also derives an immutable evaluation from
the reverified scores. It reports per-condition correct counts and the two
preregistered paired count deltas, retains digest-identified per-probe outcomes,
keeps selective abstentions and invalid answers distinct, and marks unavailable
or truncated outputs unscoreable. Per-probe correctness deltas expose whether
aggregate changes came from broad shifts or a small subset of probes. Evaluation reload
recomputes the digest and score semantics from the stored plan and score
artifacts. These are descriptive outcomes for one preregistered task, not
evidence of effect, improvement, or learning.

`build_ordinary_chat_history_intervention_cohort_summary` combines verified
evaluation artifacts from one session, task, scorer, serving-model identity,
generation configuration, shared non-history prompt, and exact selected-history
projection. It requires a complete trial sequence from
index zero in full six-trial counterbalance blocks, so an interrupted or
omitted trial prevents a seemingly complete cohort summary. It verifies that
the six scheduled orders are distinct and each occurs once per block. It
reports paired correct-count deltas and paired per-probe outcomes for every
trial, aggregates
correctness and outcome transitions per probe across scoreable repetitions,
reports paired probe gains, losses, ties, and outcome-transition counts, and
reports restoration-score stability while retaining unscoreable outcomes in
the trial count. Each planned comparison is also stratified by the six exact
condition orders, with condition positions, paired score deltas, and per-probe
outcomes in each order, so position-dependent patterns stay visible instead of
being hidden in the pooled aggregate. It verifies paired probe identities and
probe-level deltas across trials and against aggregate deltas. This is a
descriptive within-task summary; it does not establish transfer, generalization,
improvement, or learning. Restoration reports aggregate score stability, exact
output-digest stability, and whether the same per-probe outcome pattern
returned as separate measures. The cohort rebuilds
restoration flags from paired condition metrics and rejects inconsistent score
or output-digest stability claims. Restoration stability is also stratified by
condition order, including per-probe outcome transitions. New summaries use
schema v6; v2 through v5 summaries remain verifiable in their original shapes.
`OrdinaryChatHistoryInterventionStore.persist_cohort_summary` reloads each
evaluation through its protocol, result, scoring plan, and score artifacts
before publishing the summary immutably. `load_cohort_summary` repeats those
checks and verifies the summary digest on reload.

`execute_ordinary_chat_history_intervention` now supplies the dormant
three-condition orchestration boundary. It follows the frozen counterbalanced
order, requires a separate receipt-verification owner to bind every receipt to
the exact prompt, output, serving identity, and generation configuration, then
passes outputs to a scorer under freshly generated opaque sample IDs and a
shuffled order. The runner rejects anything other than completed,
non-truncated, non-fallback inference and requires the scorer to echo the bound
scoring-plan digest, scorer identity digest, and blinded-scoring posture. Score
artifact IDs and digests are copied into the result packet; output text and
score values are not retained by the runner. The runner does not
instantiate a model, and no live run has been performed. Integrators must
provide owner-backed callbacks; a callback's presence alone is not proof, and
the persisted result verifier continues to distinguish internal linkage from
independent artifact verification.

Before the first inference call, the runner publishes one immutable,
nonce-bound execution claim for the protocol. A second execution attempt is
rejected even if the first process stopped before producing a result. Such a
trial is censored as interrupted; continuing requires a newly scheduled trial,
so an operator cannot silently rerun the same preregistration and retain only
the more favorable outputs. Result persistence also requires that execution
claim. This is a one-shot custody boundary, not crash-resume support.

Protocol v3 binds a distinct scorer identity digest and a cohort digest over
the session, task, scoring plan and scorer,
serving-model identity, generation configuration, shared prompt, and
selected-history projection. The result v2 packet binds each condition's
outputs and scores back to that protocol. The
`build_ordinary_chat_history_objective_scoring_plan` helper freezes an existing
deterministic affine prediction task and evaluator source identity. The scoring
plan's question must occur in all three matched prompts, and
`persist_protocol(..., scoring_plan=...)` stores the private oracle plan before
the intervention runner can start. `OrdinaryChatHistoryAffineObjectiveScorer`
receives the shuffled, opaque samples and reuses SentientOS's deterministic
integer oracle. It publishes immutable `ordinary-history-score-*` artifacts
with the protocol and plan digests, output digest, opaque sample ID, bounded
score payload, and scorer identity digest. Result persistence and reload
recompute each score against the stored task plan. This verifies score
semantics under the bound local evaluator source; the source digest is not a
cryptographically authenticated scorer identity. New score artifacts require
protocol v3; protocol v1 and v2 artifacts remain readable for audit. After
evaluator source changes, prior plans and score artifacts remain loadable and
retain their digest bindings, but automatic
semantic revalidation reports false; new scoring refuses a source mismatch.

The intervention store allocates a durable sequential schedule per source
session, task commitment, scorer plan and identity, serving-model identity,
generation configuration, shared prompt, and selected-history projection. It
creates an initial matched prompt bundle to derive that cohort identity before
allocating a trial index.
`next_trial_index` exposes the next slot before final condition ordering;
protocol persistence claims that slot immutably and
rejects skipped indices and a different protocol reusing a slot. The runner
requires the matching sequential schedule claim before executing. Existing v1
and v2 protocols and v1 schedule claims remain readable for audit; only v3
protocols use model-and-context-scoped schedules.

`OrdinaryChatHistoryInterventionStore.prepare_intervention` now joins the
preparation path: it builds the deterministic affine task and private scorer
plan, requires that task's question to be the exact current message, reads the
next scheduled index, creates the verified history-present/withheld/restored
prompt bundle, and persists the scorer plan, protocol, and schedule claim. It
returns the frozen artifacts with `inference_started=false`; calling it does
not invoke a model.

`OrdinaryChatHistoryChatInferenceAdapter` now adapts the existing `ChatInference`
and `verify_stored_chat_invocation` interfaces. It binds calls to the protocol's
source session and user turn, adds protocol and condition lineage to each call,
checks the current model identity and exact prompt digest before each
generation, and validates the persisted
receipt's model identity, prompt and output digests, generation configuration,
completion status, truncation state, and fallback state. The receipt verifier
returns those digest fields as part of its verified summary. This is a code
integration only; it has not been called against a live model or serving
session.

Ordinary fallback turn lineage also records a bounded retrieval posture:
`selected`, `provider_returned_no_context`, `provider_unavailable`,
`provider_failed`, `context_validation_failed`, `prompt_budget_unavailable`,
`prompt_budget_rejected`, or `not_considered`. This distinguishes a verified
history exposure from common absence and omission paths during later audit. It
does not claim that the model used the selected context. The selected IDs,
digests, and posture are copied to the assistant turn and compared with the
receipt's caller lineage during idempotent recovery; legacy turns without this
lineage remain recoverable under their earlier contract. Provider failures
remain non-blocking for ordinary chat, and no raw prompt or exception text is
retained. When a history packet is selected, the exact prompt block's digest is
also saved on the assistant turn and checked through the receipt's caller
lineage. New chat responses expose this as
`prompt_block_digest` in
`sentientos.ordinary_developmental_history_exposure:v2`; legacy responses keep
the v1 shape. The exposure reports `influence_posture` as `not_measured`, so
the digest establishes what was presented, not whether the model used it. When
operator feedback cites a v2 exposure, its v7 feedback record preserves the
same prompt-block digest with the existing unverified-report posture. The digest
is an opaque content identity: consumers cannot reconstruct prompt text from it,
and it does not show attention or influence. The v7 reader also requires the
report's conversation citations to include the assistant turn and response
digest that the exposure describes.

Ordinary-chat prompt guidance now distinguishes digest-verified record
integrity from the truth of claims inside a record. When a selected packet
contains nested operator feedback, ordinary chat is instructed to retain its
`operator_assertion_unverified` posture and describe it only as an operator
report. It may use the linked history-exposure metadata to understand what was
available to the earlier assistant turn, but that metadata is not evidence of
model reliance, report accuracy, or learning. Conversation citations in that
packet identify turns by digest; ordinary chat does not infer their text from
those identities and compares a report with prior dialogue only when the exact
cited text is present in its session history.

Resident prompt assembly selects at most four verified memory records. Omitting
additional records because of that context cap or the character budget is a
selection limitation, not incomplete source verification: the context reports
`matching_records_omitted` while retaining the underlying retrieval posture when
every inspected source passed. Actual rejected or budget-deferred sources still
produce a partial-verification retrieval posture. A receipt-backed CPU fixture
checks five verified records from one source session against the four-record
prompt cap.
