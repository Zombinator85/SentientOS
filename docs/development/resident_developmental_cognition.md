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
`sentientos.resident_developmental_cognition_config:v1`. The file has exact
fields for enabled posture, separate history and composition-state roots,
allowed World-State source kinds, fact/retrieval bounds, and the opt-in paired
comparison. An absent or disabled configuration performs no developmental
model call, admission issuance, or write. Unknown, malformed, contradictory,
or unusable configuration degrades only this surface and records the reason.

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
does not load a model, admit a call, or grant serving authority. On the next daemon tick with an exact World-State
snapshot, the configured resident owner reads the request through bounded
no-follow file custody on POSIX. The current private publication and cognition
state owners remain unsupported on Windows; the staging command reports that
platform blocker and does not fall back to an ordinary write. If eligible prior developmental history exists, the
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

Native Windows staging is unsupported; this command does not use a weaker
fallback publisher. WSL is only a candidate supported host when both the daemon
and all three commands run inside that same POSIX installation and share its
exact custody roots. No cross-environment request copying or Windows/WSL
handoff has been verified here. Model-serving activation and each inference
remain subject to their existing independent authorization and custody paths;
these commands create no grants.

Every projection and observation declares historical context to be read-only,
non-authoritative, non-policy, non-current-truth, and outside canonical explicit
user retention. Developmental history uses a physically separate configured
root and does not widen canonical retention semantics.

## Fourth substrate: prior epistemic state

Cognition can receive a separately typed, prior-tick epistemic projection binding exact proposition IDs, state IDs/digests, generations, and evidence-set digests. Current World-State evidence outranks a conflicting stale position for current-condition reasoning. Same-tick projections fail closed, so a cognition cannot certify its own update. See [persistent epistemic state](../architecture/persistent_epistemic_state.md).
