# Durable-learning target-host acceptance policy

**Status: draft. No target-host evidence has been accepted under this policy.**

## Scope

This policy governs review of the no-model, supervised Windows AppContainer
access-matrix run for the condition-scoped durable-learning worker. It defines
what a completed probe can establish and what additional evidence is required
before any later experiment can claim a retention contrast. The access probe
does not invoke a model, score an answer, write developmental history, or
establish learning.

The access-probe completion artifact is protocol-specific and binds the branch
preflight, AppContainer profile pair, runtime access setup, per-condition probe
manifests, worker RPC completions, and registry inventories. Review must use
the exact persisted artifacts and their digests, not console output or a
summary copied from another run.

## Required access-matrix evidence

Review both conditions independently. Every item below must be present and
internally consistent for the probe result to be accepted as a bounded access
observation:

1. **Protocol and profile binding.** The persisted protocol, branch preflight,
   profile-pair artifact, and access-probe completion artifact must agree on
   protocol ID and digest, condition names, branch IDs, profile IDs, and
   AppContainer SIDs. The two conditions must use distinct profile identities.
2. **Process binding.** Each RPC exchange must bind to the observed worker
   process identity, process-start nonce, and expected AppContainer SID. Both
   workers must return a natural zero exit after the probe and registry
   inventory operations. Partial launch, missing exit, a reused or ambiguous
   process identity, or an unresolved interruption is a rejection.
3. **Own sentinel.** The worker must open its own sentinel for read and write,
   match its pinned volume and file identity, read the exact pinned bytes,
   verify end of file, write those same bytes, and flush successfully.
4. **Peer and scorer sentinels.** Each worker's read/write open attempt for the
   peer sentinel and supervisor scoring sentinel must fail with Win32 access
   denied (error 5). Any successful open, different error, or missing attempt
   is a rejection.
5. **Supervisor readback.** After worker exit, the supervisor must open all
   three sentinels read-only and match each pinned identity, content digest,
   and end of file. This verifies the sentinels remained the expected objects;
   it does not turn the worker's report into an independent security proof.
6. **Registry and profile state.** The paired registry inventories and
   profile-data inventory baseline must be present, digest-valid, condition
   bound, and reloadable. Any unexplained condition asymmetry or inventory
   drift must be resolved before the artifact can be accepted.
7. **Runtime access setup.** The runtime grant artifact must identify every
   granted root and report successful bounded grants. Each granted root must
   remain disjoint from all own, peer, and scorer sentinel custody. Unresolved
   or partial grants reject the run.

Acceptance records the limited finding that, during this protocol-bound run,
these two observed worker processes produced the specified open results for
these pinned sentinels and registry inventories. The finding is time- and
host-specific. It does not establish that no inherited handle, alternate
capability, broker, or unobserved path can bypass the access checks, nor that
all profile, filesystem, registry, or operating-system state was inventoried.

## Review record

An independent reviewer should record:

- reviewer identity and review time;
- run-operator identity, recorded alongside the reviewer identity;
- protocol ID and digest;
- branch-preflight ID and digest;
- profile-pair artifact ID and digest;
- access-probe completion artifact ID and digest;
- both registry-inventory artifact IDs and digests, plus the registry baseline
  ID and digest;
- both profile-data inventory artifact references;
- the Windows host identity and OS build observed during the run;
- disposition: `accepted_bounded_access_observation`, `rejected`, or
  `insufficient_evidence`;
- each failed or unresolved criterion and the evidence reference supporting the
  disposition.

The record must validate against
[`durable_learning_host_acceptance_review.schema.json`](durable_learning_host_acceptance_review.schema.json).
An `accepted_bounded_access_observation` disposition requires every listed
criterion to be accepted. Rejected or incomplete reviews cannot set the
bounded-acceptance flag. The schema fixes all isolation, retention, learning,
improvement, and authority claims to false.

The review artifact digest is `digest_payload` over the review object with
`artifact_id` and `artifact_digest` omitted; the artifact ID is
`devexp-durable-learning-host-access-review-` followed by the first 24 digest
hex characters. The schema checks shape and fixed claim limits. The review
helper recomputes the canonical digest, while the protocol store reloads each
cited source artifact and compares its ID and digest before persisting or
loading a review. This writer and loader record only an independent review;
they do not create target-host evidence or make an unrun probe acceptable. No
target-host review has been recorded under this policy.

The protocol store's `retention_evidence_inventory` v2 discovers protocol-bound
reviews, reloads each one through the same source-artifact checks, and reports
its disposition. An accepted bounded access observation remains separate from
retention eligibility; the inventory never promotes the latter. Consumers can
validate the response against
[`durable_learning_persisted_gate_evidence.schema.json`](durable_learning_persisted_gate_evidence.schema.json).

The review validator rejects reviewer and operator identity strings that are
equal after trimming and case-folding. These identities are supplied by the
reviewer: the current host workflow does not authenticate either person or
independently establish their organizational independence.

The review record must not overwrite or amend the immutable run artifacts. A
changed protocol, profile, sentinel, worker executable, runtime grant, host
build, or ACL setup requires a new protocol-bound acceptance run. An
interrupted run is not resumed or counted as a successful observation.

## Claims this acceptance cannot promote

Even an accepted bounded access observation leaves all of these false:

- `process_isolation_verified`;
- `filesystem_isolation_verified`;
- `retention_contrast_eligible`;
- model attention, causal use of history, performance improvement, or learning.

Before a retention contrast can be eligible, separate evidence and a further
review must establish the complete process and state boundary: no inherited
handle or alternate capability can cross conditions; all persistent
condition-local filesystem, registry, profile, and service state is accounted
for; starting state is equivalent except for the preregistered experience
condition; scorer and answer-key custody is inaccessible to both workers; and
recovery cannot replay, repair, or import unregistered state. The experiment
must then bind held-out outcomes to the exact consumed history and retain
independent scoring and interruption evidence. The access-matrix artifact
alone can never promote those gates.

The implementation currently keeps process isolation, filesystem isolation,
and retention eligibility false. A reviewer must not change those fields by
editing an artifact. Any future promotion requires a separately versioned,
machine-checked evidence contract and a new protocol; this draft does not
authorize it.

The complete-boundary verifier also requires the available/withheld workers'
inherited-handle inventories to declare the same inventory scope, and applies
the same paired-scope check to broker-capability inventories. This prevents a
review from treating different observation coverage as a clean condition
comparison. Matching scope declarations do not prove that the collector saw
every handle or capability; completeness remains a claim in the source
artifacts that requires independent review.

## Current implementation boundary (2026-11-25)

The condition worker can recover a condition-local receipt index and construct
a read-only consolidation snapshot linked to persisted prompts, outputs, and
receipt digests. Recovery startup now also reconstructs the sealed acquisition
bundle and requires its receipt ID/digest pairs to exactly match the staged
invocation-receipt store's allowlist, including rejecting unreferenced extras.
Recovery reloads the staged store index against the verifier's pinned root and
requires the artifact digest and verifier allowlist to agree before that
cross-store comparison. This closes a cross-store binding gap; it does not
independently reauthenticate the original source receipts. The snapshot
explicitly reports
`source_invocation_receipts_reverified: false`; its construction validates
the local transcript and receipt-bundle bindings, but does not reauthenticate
the original invocation receipts. The recovery owner also has inference,
comparison, and developmental writeback disabled. A pending consolidation can
only reconcile an already completed owner tick; it cannot start a new tick.

Successful receipt-recovery RPCs now persist the receipt reference-set digest
and count together with positive checks for exact bundle/store equality, store
index reload, and verifier-allowlist agreement. The RPC verifier and recovery
artifact loader validate those fields against the requested task count and
fixed false claims. This makes the startup gate inspectable in the persisted
run; it does not elevate the gate into source-receipt reauthentication or a
host-isolation claim.

There are no accepted target-host access-probe or boundary-acceptance records
in the current experiment artifacts. Therefore this implementation state
supports read-only preparation and bounded journal recovery only. It does not
support enabling first-time consolidation, retention writeback, or a
retention-contrast claim. These transitions require the protocol-specific
host acceptance evidence and subsequent review described above; changing the
worker flags or synthesizing acceptance artifacts is not evidence.
