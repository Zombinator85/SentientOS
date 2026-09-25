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

Every projection and observation declares historical context to be read-only,
non-authoritative, non-policy, non-current-truth, and outside canonical explicit
user retention. Developmental history uses a physically separate configured
root and does not widen canonical retention semantics.
