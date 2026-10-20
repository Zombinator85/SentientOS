# Resident cognitive transition live operator ingress

The live ingress is an explicit, local transport into the already admitted
`resident_cognitive_model_transition_experiment` controller.  It grants no authority:
the existing stage approval is still verified by the transition controller, while
activation, resident serving, inference, and developmental writeback remain owned and
admitted independently.

## Configuration and custody

Configuration schema v1 contains `enabled`, the authenticated `installation_identity`,
exact `protocol_id` and `protocol_digest`, fixed `request_custody`, fixed `journal_custody`,
and `journal_identity`. The two fixed relative values are respectively
`state/resident-cognitive-transition/operator-requests` and
`state/resident-cognitive-transition/transition.journal.jsonl`. Aliases and arbitrary
request or journal roots are rejected. V1 remains readable for status inspection, but it
has no operator trust anchor, so request recovery and processing fail closed.

Production request admission requires configuration schema
`sentientos.resident_cognitive_transition_live_config:v2`, which adds the expected
`operator_trust_catalog_version` and `operator_trust_catalog_digest`. The catalog is read
only from the fixed installation path
`state/resident-cognitive-transition/operator-trust-catalog.json`; its canonical content,
version, digest, public-key identifiers, validity intervals, duplicate-free operator/key
tuples, and revocation state are checked at composition. The configured digest is the
operator-provisioned anchor. A catalog's own digest provides integrity only and does not
authenticate who provisioned it. Missing or invalid v2 trust prevents live request
composition.

Request packets use
`sentientos.resident_cognitive_transition_operator_request:v1`.  A packet binds its
content-derived request ID and digest, installation, protocol and transition identities,
requested stage, prior phase, journal head, exact stage approval and digest, subordinate
approval artifacts and their IDs/digests, operation and correlation IDs, operator
identity/provenance, creation and expiry times, and `grants_authority=false`. An operator
signs the exact canonical request claims with Ed25519 under a domain-separated payload;
the signed claims include every request field except the detached provenance envelope
and content-derived request IDs. The daemon has no signing API or private-key access.
Its verifier binds the envelope identity to the request identity, looks up the exact
operator/key/algorithm tuple in the immutable catalog, checks key validity and current
revocation status, and verifies the signature. The CLI only creates the packet with
exclusive-create semantics and never issues an approval or executes a stage.

Request hashes and provenance-envelope hashes provide byte integrity only; they are not
signatures. Missing verifier configuration, unknown operators, revoked or out-of-window
keys, changed request claims, and invalid signatures fail closed before request recovery
or stage execution. The explicitly synthetic end-to-end rehearsal creates a temporary
operator keypair, installs only its public key in its isolated trust catalog, and signs
its synthetic requests before sending them through the same verifier. The private key is
not written to installation custody or exposed to the daemon.

Receipts form a hash chain at
`state/resident-cognitive-transition/operator-request-receipts.jsonl`.  Any request ID
already in that custody returns `already_consumed` without calling the controller.  The
request file is never deleted or rewritten.

## Authenticated operator in canonical planning

When a completed stage receipt is projected for canonical campaign planning, the owner
re-verifies the exact request provenance against its configured trust verifier and emits
the authenticated operator identity, signing-key ID, claims and provenance digests, signed
time, and pinned trust-catalog version and digest in the v3 verified-stage projection.
The campaign planner validates the bounded shape and digest formats, then carries this
record into both the next-stage plan and any active-trial binding. It remains descriptive
provenance: it does not choose an approval, bind a request to a campaign trial by itself,
grant authority, or permit execution. Missing, revoked, or otherwise unverifiable operator
provenance prevents planning; existing v2 projections without authenticated identity are
not promoted into canonical plans.

## Supplied stage-approval inspection

`RuntimeMaintenanceSurfaces.plan_resident_cognitive_transition_stage_admission`
accepts one caller-supplied stage-approval object and returns a read-only
`sentientos.resident_cognitive_transition_stage_admission_plan:v1` projection.
The controller rechecks the supplied digest, exact next-stage and prior-phase
binding, current journal head, protocol and installation identities, serving and
history boundary, validity window, and synthetic-test posture against a fresh
read of current state. It does not read the request mailbox, select or mint an
approval, append a journal entry, consume a request, or invoke the stage owner.

A `stage_approval_candidate_state_bound` result means only that the supplied
object is internally digest-consistent and bound to the observed state. The
approval digest is unkeyed, so this inspection does not authenticate the
operator or prove that an operator issued the object. The result explicitly
keeps `operator_origin_authenticated=false`, `execution_allowed=false`, and
`grants_authority=false`; live stage processing separately verifies signed provenance,
performs fresh state validation, and leaves all effect owners' independent admissions
intact.

## Runtime ordering and status

`RuntimeMaintenanceSurfaces.process_resident_cognitive_transition_request` calls the
configured ingress exactly once.  The daemon maintenance tick invokes it after ordinary
resident developmental cognition.  It therefore cannot drain a mailbox or infer during
a resume stage: ordinary cognition can resume only on a later tick.

The read-only live status binds enabled/configured posture, protocol and transition,
phase and journal head, quiescence, resident session/model identity, latest consumed
request/result, and interrupted/complete posture. For an interrupted transition it also
exposes the controller's exact `reason`, `outstanding_stage`, and `replay_forbidden`
values, plus the bounded `semantically_verified_stage_entry_digests` list of entries
whose subordinate evidence passed semantic verification. Status inspection consumes no
request and performs no stage transition or journal mutation.

This remains bounded live-runtime composition and synthetic test evidence.  No network
surface, autonomous cadence, automatic retry, rollback, stage loop, or second-stage
advance is introduced.  Production temporal A-to-B-to-A evidence with actual hardened
commissioned models remains uncollected and is the next required bridge.
