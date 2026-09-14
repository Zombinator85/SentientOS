# Maintenance authority continuity eligibility

`maintenance_authority_continuity` is the planning-eligibility contract for the first
bounded authority-inheritance mechanism in SentientOS. It prepares a separately
reviewed future controller; it does not grant authority, derive a profile, issue a
lease, mutate the repository, change daemon configuration, invoke maintenance, or
adopt or restart runtime code.

The definition binds subsystem `maintenance` and principal
`deterministic_maintenance_authority_continuity_controller` to this exact effect set:

- `exact_prior_maintenance_authority_generation_read`
- `exact_completed_maintenance_generation_evidence_read`
- `exact_successor_repository_state_read`
- `bounded_successor_maintenance_authority_derive`
- `successor_maintenance_configuration_generation_write`
- `maintenance_authority_continuity_receipt_write`

These effects describe continuity between generations, not candidate creation or
admission, lease execution, implementation, validation, Git operations, publication,
provider or credential access, arbitrary policy/grant creation, or runtime adoption.

## Present and intended behavior

The [wake-daemon adoption contract](maintenance_wake_daemon_adoption.md) says exact
base/component staleness fails closed **in this proving phase** while separately
reviewed authority continuity remains possible. The present behavior is:

```text
successful maintenance changes repository
-> old exact-base authority becomes stale
-> wake owner blocks
-> operator must presently create new authority/configuration
```

This fail-closed behavior remains unchanged by this admission task. It is a present
proving posture, not a permanent principle that requires human re-authoring between
every successful generation. The intended, still-deferred behavior is:

```text
successful maintenance generation
-> prove exact successor repository state
-> prove predecessor authority and successful closure
-> derive same-or-narrower successor authority generation
-> continue bounded maintenance under the successor generation
```

## Predecessor and exact-successor proof

A future controller must consume one exact prior authority/profile generation, the
still-valid constraints from that generation, canonical proof of an legitimately
admitted and successfully completed maintenance task, and exact successor-state
evidence. It should bind existing canonical identities for the activation profile,
standing grant, selector policy, admitted lease, implementation, validation, commit,
publication or absorption, terminal closure/custody, and wake/autonomy/watchdog
evidence when needed. It must not reconstruct success from loose file presence or
duplicate evidence already bound by a canonical terminal artifact.

An exact local base-ref advancement or exact fast-forward tracked-base advancement may
qualify when existing evidence unambiguously proves it. Publication, PR creation, or
tree equivalence alone is insufficient: an equal tree is not exact commit custody.
Merge, rebase, or squash continuity stays deferred unless the authoritative successor
and its relation to the validated result can be proved exactly. An unproven hosted
transformation must fail closed.

## Same-or-narrower inheritance

The successor may preserve or reduce prior operator-authored policy, but success does
not widen it. It may not increase authority classes, allowed path prefixes, candidate
kinds, file or changed-line budgets, implementation/validation/wall-clock budgets,
attempts, corrective retries, publication retry/backoff authority, landing modes,
executable authority, or remote/network authority. It may not extend predecessor
expiry without a separately admitted future capability. Exact base-linked identities
and digests may change solely to bind the proven successor; that rebinding is not an
authority widening.

Future effectful goals must affirm `successful prior maintenance generation`, `exact
successor repository state`, `same or narrower authority`, and `bounded successor
authority`. Goals requesting arbitrary widening or policy/grant creation, a new
authority class or path expansion, expiry extension, disregard of predecessor
authority, an arbitrary or unverified successor, publication/PR-only proof, model
self-grant, credentials, providers, network authority, runtime adoption, or OS
scheduler installation are ineligible.

The registry therefore reports `scaffolded` and `eligibility_only`, requires governed
control-plane admission and an audit receipt, and explicitly defers successor-state
observation, predecessor-proof verification, successor derivation/rendering, daemon
rebinding, post-advancement wake continuation, and runtime adoption.
