# Bounded maintenance authority continuity

`maintenance_authority_continuity` implements the derivation half of maintenance
authority inheritance.  Its admitted principal remains
`deterministic_maintenance_authority_continuity_controller` with the exact registered
effect set.  Eligibility does not itself grant capability; each invocation consumes
an already operator-established continuity policy and verified predecessor custody.

## Immutable lineage

The controller defines closed, digest-bound v1 records for a persistent continuity
policy, maintenance authority generation, completed-generation evidence, exact
successor evidence, and a continuity receipt.  The policy names generation zero once.
Later generations use ordinal filenames under its exact external custody roots; no
glob, timestamp, newest-file, or caller-selected later-generation authority is used.
Every adjacent descriptor and receipt is verified, and orphaned, corrupt, conflicting,
or branched custody fails closed.

Generation descriptors bind the exact activation manifest, profile bundle, base SHA,
predecessor generation, and prior continuity receipt.  A derived generation is the
same schema as generation zero, so generation 1 can be the predecessor for generation
2 without a new operator-authored profile.

## Closure and successor proof

Completed-generation evidence must bind admission, lease, implementation, passing
validation, exact validated commit, successful landing, terminal completion, and
integrity evidence identities.  Every required status must be successful; waiting,
failed, paused, incomplete, ambiguous, or unlanded work is rejected.

The implemented successor mode is only `local_fast_forward_base_ref`.  Evidence must
show that the validated commit is the successor, its parent and compare-and-swap old
object are the predecessor base, the exact local base/tracked ref advanced to it, the
checkout synchronized to it, and current clean repository truth still equals it.
PR/publication requests, payload echoes, equal trees, rewrites, merges, rebases, and
squashes are not accepted.

## Same-or-narrower derivation

The successor manifest is copied through the canonical maintenance activation-profile
renderer, changing only its deterministic generation identity, output custody path,
and proven base SHA.  Authority classes, candidate kinds, paths, budgets, attempts,
corrective retries, validation bounds, landing/ref/executable authority, validity
start, and expiry must remain the same or narrower.  The controller neither creates
operator approval nor extends expiry.  Every generated profile artifact is checked by
the existing profile-bundle verifier.

Writes are immutable, exclusive, deterministic, and no-clobber.  Exact replay returns
the existing generation; conflicting partial output blocks.  One `derive-next` call
derives at most one ordinal and writes a narrow receipt linking the predecessor,
closure evidence identities, exact successor proof, narrowing result, successor
manifest/profile, generation descriptor, and prior receipt.  Bodies, prompts,
credentials, transcripts, and validator output are never copied.

## CLI and authority boundary

`python scripts/maintenance_authority_continuity.py` exposes `doctor`, `inspect`,
`inspect-receipts`, and `derive-next`.  Inspection is read-only.  Derivation renders
external configuration custody only.  The module contains no Git, provider, network,
candidate, lease, implementation, validation, commit, publication, daemon, restart,
or runtime-adoption actuator.

Automatic wake-daemon rebinding, post-advancement wake continuation, runtime code
adoption, hosted transformations, authority widening, and expiry extension remain
deferred.  The generation-N wake owner may therefore still fail closed after the base
changes until a separately authorized adoption boundary is implemented.
