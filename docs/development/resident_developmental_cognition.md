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
Its output says `staged_not_authorized`: it does not load a model, admit a call,
or grant serving authority. On the next daemon tick with an exact World-State
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
acquisition or performance.

Every projection and observation declares historical context to be read-only,
non-authoritative, non-policy, non-current-truth, and outside canonical explicit
user retention. Developmental history uses a physically separate configured
root and does not widen canonical retention semantics.

## Fourth substrate: prior epistemic state

Cognition can receive a separately typed, prior-tick epistemic projection binding exact proposition IDs, state IDs/digests, generations, and evidence-set digests. Current World-State evidence outranks a conflicting stale position for current-condition reasoning. Same-tick projections fail closed, so a cognition cannot certify its own update. See [persistent epistemic state](../architecture/persistent_epistemic_state.md).
