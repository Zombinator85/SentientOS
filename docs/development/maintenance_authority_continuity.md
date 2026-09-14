# Bounded maintenance authority continuity

`maintenance_authority_continuity` implements the derivation half of maintenance
authority inheritance.  Its admitted principal remains
`deterministic_maintenance_authority_continuity_controller` with the exact registered
effect set.  Eligibility does not itself grant capability; each invocation consumes
an already operator-established continuity policy and verified predecessor custody.

## Immutable lineage

The controller defines closed, digest-bound records for a persistent continuity
policy, maintenance authority generation, canonical completed-generation evidence, exact
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

Authority-bearing v2 completed-generation evidence names the canonical task journal,
lease, validation result, commit plan/result, publication request/result, and terminal
closure event by absolute path and exact digest. Derivation reloads each artifact
from its schema-owned state-root directory, verifies its native seal, replays the
journal, and cross-checks task, lease, generation/base, validation, commit, landing,
and closure identities. Missing, moved, mutated, stale, failed, ambiguous, or
non-terminal custody fails closed. The old v1 completion and successor formats are
diagnostic-only and can never authorize derivation; they are not silently upgraded.

The implemented successor mode is only `local_fast_forward_base_ref`. The canonical
publication result proves that the validated commit is the successor, its parent and
compare-and-swap old object are the predecessor base, the exact local base/tracked ref
advanced to it, and the checkout synchronized to it. At derivation time the controller
also performs read-only Git observations of the exact ref, symbolic HEAD, clean
index/worktree/untracked state, and absence of an ambiguous in-progress operation.
Caller-asserted SHAs and cleanliness booleans are not trusted.
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
external configuration custody only. The module contains no Git mutation, provider,
network, daemon, restart, or runtime-adoption actuator. It reuses canonical maintenance
validators and read-only repository observation helpers; it never fetches, pulls,
publishes, or moves a ref.

Automatic wake-daemon rebinding, post-advancement wake continuation, runtime code
adoption, hosted transformations, authority widening, and expiry extension remain
deferred.  The generation-N wake owner may therefore still fail closed after the base
changes until a separately authorized adoption boundary is implemented.
