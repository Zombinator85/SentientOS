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
