# Resident cognitive transition live operator ingress

The live ingress is an explicit, local transport into the already admitted
`resident_cognitive_model_transition_experiment` controller.  It grants no authority:
the existing stage approval is still verified by the transition controller, while
activation, resident serving, inference, and developmental writeback remain owned and
admitted independently.

## Configuration and custody

The exact configuration schema is
`sentientos.resident_cognitive_transition_live_config:v1`.  It contains only `enabled`,
the authenticated `installation_identity`, exact `protocol_id` and `protocol_digest`,
fixed `request_custody`, fixed `journal_custody`, and `journal_identity`.  The two fixed
relative values are respectively
`state/resident-cognitive-transition/operator-requests` and
`state/resident-cognitive-transition/transition.journal.jsonl`.  Aliases and arbitrary
request or journal roots are rejected.  Disabled or absent composition performs no
transition effect.

Request packets use
`sentientos.resident_cognitive_transition_operator_request:v1`.  A packet binds its
content-derived request ID and digest, installation, protocol and transition identities,
requested stage, prior phase, journal head, exact stage approval and digest, subordinate
approval artifacts and their IDs/digests, operation and correlation IDs, operator
identity/provenance, creation and expiry times, and `grants_authority=false`.  The CLI
only creates the packet with exclusive-create semantics and never issues an approval or
executes a stage.

Receipts form a hash chain at
`state/resident-cognitive-transition/operator-request-receipts.jsonl`.  Any request ID
already in that custody returns `already_consumed` without calling the controller.  The
request file is never deleted or rewritten.

## Runtime ordering and status

`RuntimeMaintenanceSurfaces.process_resident_cognitive_transition_request` calls the
configured ingress exactly once.  The daemon maintenance tick invokes it after ordinary
resident developmental cognition.  It therefore cannot drain a mailbox or infer during
a resume stage: ordinary cognition can resume only on a later tick.

The read-only live status binds enabled/configured posture, protocol and transition,
phase and journal head, quiescence, resident session/model identity, latest consumed
request/result, and interrupted/complete posture.  Status performs no transition.

This remains bounded live-runtime composition and synthetic test evidence.  No network
surface, autonomous cadence, automatic retry, rollback, stage loop, or second-stage
advance is introduced.  Production temporal A-to-B-to-A evidence with actual hardened
commissioned models remains uncollected and is the next required bridge.
