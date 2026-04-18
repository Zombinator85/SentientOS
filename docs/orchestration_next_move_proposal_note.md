# Orchestration Next-Move Proposal Note

`orchestration_next_move_proposal.v1` is a bounded constitutional **proposal artifact** for "what should happen next" in orchestration.

## Signals used

It is derived only from existing orchestration signals:

- delegated judgment
- next-venue recommendation
- orchestration outcome review
- orchestration venue-mix review
- orchestration operator-attention recommendation
- existing escalation/operator-required state

## What it is (and is not)

- **Delegated judgment** states the current bounded recommendation from constitutional evidence.
- **Next-venue recommendation** states relation-aware venue preference (`affirming`, `nudging`, `holding`, `escalating`, `insufficient_context`).
- **Next-move proposal** fuses those signals into one machine-readable, proof-visible proposal object with:
  - proposed venue
  - proposed posture (`expand`, `consolidate`, `audit`, `hold`, `escalate`)
  - executability classification
  - operator/escalation requirement state

The proposal is explicitly non-sovereign and non-authoritative:

- `diagnostic_only: true`
- `non_authoritative: true`
- `decision_power: none`
- `proposal_only: true`
- `does_not_execute_or_route_work: true`
- `does_not_override_delegated_judgment: true`
- `requires_operator_or_existing_handoff_path: true`

It does not execute, route, or admit work by itself.

## Packetization gate and operator action brief (held/escalated handoff preparation)

`orchestration_packetization_gate.v1` remains the bounded gate for whether next-move packetization is:

- `packetization_allowed`
- `packetization_allowed_with_caution`
- `packetization_hold_operator_review`
- `packetization_hold_insufficient_confidence`
- `packetization_hold_fragmentation`
- `packetization_hold_escalation_required`

When gate outcome is held/escalated, `operator_action_brief.v1` may be emitted as a compact
operator guidance artifact (`glow/orchestration/operator_action_briefs.jsonl`) derived only from existing
signals already present in orchestration state:

- packetization gate outcome
- trust/confidence posture
- next-move proposal
- operator-attention recommendation
- next-move proposal review classification (where already derived)
- existing operator/escalation requirement state

Bounded intervention classes:

- `approve_and_continue`
- `review_fragmentation`
- `resolve_insufficient_context`
- `resolve_escalation_priority`
- `inspect_recent_orchestration_stress`
- `manual_external_trigger_required`

The operator action brief is distinct from packetization and handoff packet artifacts:

- packetization gate decides **allow/caution/hold** only
- handoff packet carries venue/task payload only
- operator action brief states **what human intervention type is needed next** when held

The operator action brief explicitly does **not**:

- override packetization outcomes
- convert held packets into executable packets
- add new venues, execution paths, or authority surfaces
- execute, route, or invoke external tools directly
- become a workflow engine or sovereign planner

## Operator-resolution receipt (ingested operator outcome only)

`operator_resolution_receipt.v1` records the operator's response to a held/escalated
`operator_action_brief.v1` as append-only constitutional history in
`glow/orchestration/operator_resolution_receipts.jsonl`.

Operator brief vs operator resolution:

- **Operator action brief** = what intervention class is requested by orchestration.
- **Operator resolution receipt** = what the operator actually decided/returned.

Bounded resolution kinds:

- `approved_continue`
- `approved_with_constraints`
- `declined`
- `deferred`
- `supplied_missing_context`
- `redirected_venue`
- `cancelled`

Bounded lifecycle visibility from brief to receipt:

- `brief_emitted`
- `operator_resolution_received`
- `operator_approved_continue`
- `operator_approved_with_constraints`
- `operator_declined`
- `operator_deferred`
- `operator_redirected`
- `operator_supplied_missing_context`
- `fragmented_unlinked_operator_resolution`

Resolution receipt ingestion means **operator guidance was ingested**, not that execution happened.
It remains receipt-only (`ingested_operator_outcome`, `receipt_only`, `decision_power: none`) and
does not self-authorize execution or bypass packetization/admission. Any follow-on action still
requires existing trigger paths and authority surfaces.

## Bounded operator-resolution feedback integration (non-executing)

Operator resolutions are now also consumed as bounded feedback through a compact
`operator_resolution_influence.v1` surface and reflected into:

- packetization gating (`operator_influence`, bounded hold-relief paths)
- next-move proposal visibility (`original_*` vs `current_*` proposal venue/posture visibility)
- next-venue visibility (`original_next_venue_recommendation` vs `current_next_venue_recommendation`)

Supported bounded effects:

- `approved_continue` / `approved_with_constraints`: may relax operator-review hold to cautious packetization when other coherence requirements are already satisfied.
- `supplied_missing_context`: may relax insufficient-context hold when context refs are present and fragmentation is not active.
- `redirected_venue`: may change current bounded venue recommendation/proposal visibility while preserving original delegated recommendation history.
- `declined` / `cancelled`: preserve or strengthen held/no-action posture.
- `deferred`: preserves held posture with explicit operator-response visibility.

Non-sovereign boundary invariants remain explicit on influenced surfaces:

- `operator_influence_applied`
- `does_not_imply_execution`
- `does_not_override_admission`
- `requires_existing_trigger_path_for_follow_on_action`
- `historical_operator_resolution_preserved`

What is still missing before any tighter delegated loop exists: no receipt-triggered execution,
no admission bypass, no autonomous workflow sovereign, and no direct external actuation path.

## Next-move proposal review (retrospective only)

`next_move_proposal_review.v1` provides a compact retrospective classifier over recent
`orchestration_next_move_proposal.v1` records.

It reads only existing proposal artifacts/fields and existing orchestration-derived proposal state:

- `relation_posture`
- `proposed_next_action.proposed_venue`
- `executability_classification`
- `operator_escalation_requirement_state.requires_operator_or_escalation`

Bounded review classifications:

- `coherent_recent_proposals`
- `proposal_escalation_heavy`
- `proposal_hold_heavy`
- `proposal_insufficient_context_heavy`
- `proposal_venue_thrash`
- `mixed_proposal_stress`
- `insufficient_history`

The review is descriptive and diagnostic. It does **not** plan, execute, admit, route, or
authorize work; it remains `diagnostic_only`, `non_authoritative`, `decision_power: none`,
and `review_only`.
