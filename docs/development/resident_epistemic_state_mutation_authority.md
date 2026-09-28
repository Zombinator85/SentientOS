# Resident epistemic-state mutation authority

## Definition-only registration

`resident_epistemic_state_mutation` is an operator-approved, governance-only
definition for a future, separately admitted
`deterministic_resident_epistemic_state_controller` in the `epistemics`
subsystem. This source-level catalog registration grants no capability, runtime
authority, admission, lease, or effect and constructs no controller.

```text
definition exists
!= runtime admission exists
!= controller exists
!= epistemic mutation occurred
```

The definition is an implemented governance prerequisite. It is not a composed
epistemic updating path, production evidence, or a claim of beneficial learning.
The existing owner primitives remain unchanged, and a later task must implement
and separately admit any controller.

## Exact effect vocabulary

The future controller may request bounded subsets of this exact effect surface:

1. `exact_epistemic_proposition_read`
2. `exact_epistemic_current_state_read`
3. `exact_epistemic_evidence_source_artifact_read`
4. `exact_epistemic_evidence_binding_validation`
5. `bounded_epistemic_evidence_binding_append`
6. `exact_epistemic_update_candidate_read`
7. `deterministic_epistemic_update_candidate_validation`
8. `exact_epistemic_predecessor_state_compare_and_swap`
9. `bounded_epistemic_state_generation_append`
10. `bounded_epistemic_update_event_append`
11. `epistemic_mutation_receipt_write`
12. `read_only_epistemic_post_mutation_verification`

It receives no generic filesystem, database, memory, developmental-history,
self-model, policy, goal, model, tool, shell, process, host, resource, network,
provider, credential, repository, Git, federation, admission, or action
authority.

## Two separately admitted stages

An evidence-binding admission may contain only exact proposition/source reads,
binding validation and append, and receipt verification effects:

```text
independent observation -> explicit adapter -> candidate EvidenceBinding
-> separate admission -> deterministic validation -> append -> receipt
```

A distinct state-update admission may contain only exact proposition, current
state, evidence-set and candidate reads, candidate validation, predecessor CAS,
state/update append, and receipt verification effects:

```text
current state + bound evidence -> EpistemicUpdateCandidate
-> separate admission -> deterministic validation -> predecessor CAS
-> state generation + paired update event -> receipt
```

Authority to bind evidence is not authority to change epistemic position. One
admission must not imply the other. Evidence is not truth or epistemic position;
a candidate is proposal-only, not permission, truth, or state. The future
invariant is: **Model proposes; deterministic controller validates; separate
admission permits; CAS owner commits.**

## Approval and non-authority boundary

The definition requires an exact existing proposition; source artifact identity
and digest; explicit adapter output; relation, dependency, freshness, and
reliability validation; separately admitted binding append; exact predecessor
state; a fully bound all-false-authority candidate; separately admitted state
mutation; deterministic validation; CAS; immutable state/update custody; a
durable receipt; and post-write reconstruction verification. Model output and
observed evidence confer no mutation authority.

The immutable definition approval is bound to capability
`resident_epistemic_state_mutation`, the exact definition digest, task
`register_resident_epistemic_state_mutation_definition`, and repository-operator
identity. It approves registration only:

```text
approved authority definition
!= approved evidence binding
!= approved epistemic update
```

Later cognition may consume an admitted result only as a prior epistemic
position. Epistemic position is not truth, World-State, memory, self-model,
developmental history, policy, goal, permission, or action authority.

