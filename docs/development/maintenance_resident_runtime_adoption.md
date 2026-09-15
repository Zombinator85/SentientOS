# Maintenance resident-runtime adoption

The closed `sentientos.maintenance_resident_runtime_adoption_config:v1` is a
persistent posture, not a request-time executable selector. When enabled, its
digest is checked together with the canonical continuity policy, successor
adoption configuration, optional automatic-continuity configuration, repository
identity and real root, exact interpreter realpath, canonical repository
`sentientosd.py`, module `sentientosd`, repository working directory, external
state custody, STOP marker, closed environment, and count/time bounds. Ambient
`PYTHONPATH` and `PYTHONHOME` are forbidden. The only exec contract is:

```text
<configured-python-realpath> -m sentientosd
```

## Provenance and transition machine

Before maintenance owners start, ordinary daemon startup reconstructs the
currently adopted generation from successor-adoption custody. It independently
checks exact HEAD, canonical symbolic base ref, commit tree, clean worktree, and
absence of an ambiguous Git operation. It then writes an immutable v2 launch
record under a generation directory using a deterministic process-instance
digest. Consequently, two legitimate launches in one generation retain two
records rather than overwriting a mutable `generation-N.json` pointer. Each
record binds the generation and manifest, configuration, repository observation,
interpreter, daemon entrypoint/module, cwd, exact argv, bounded environment,
PID/process instance, and startup time.

Replacement is eligible only when the canonical successor journal is exactly at
`predecessor_confirmed_quiescent`. The controller reconstructs N, verifies the
canonical N+1 generation and continuity receipt, requires consecutive ordinals
and exact lineage/digests, and rejects fabricated caller handoffs. It then
re-proves that the local repository is exactly N+1. `sentientosd` stops ordinary
stale-resident ticks at this barrier and cooperatively stops only its automatic
continuity and successor-generation owners within the configured quiescence
bound. The successor owner remains the sole owner of predecessor wake shutdown
and successor wake startup.

After those proofs, the resident journal admits exactly this v2 phase sequence:

1. `resident_adoption_intent_recorded`
2. `predecessor_resident_provenance_verified`
3. `maintenance_runtime_quiescence_confirmed`
4. `self_exec_requested`
5. `successor_launch_provenance_verified`
6. `successor_resident_readiness_recorded`
7. `resident_adoption_completed`

The pre-exec transaction binds the exact predecessor launch record, N/N+1 and
continuity identities, pending successor event, observed successor commit/tree,
and exec contract. `os.execve` receives only allowlisted inherited variables,
required sealed variables, and the exact transition marker. There is no shell,
subprocess restart, arbitrary executable/argv, checkout, reload, or rollback.

## New-image recovery and wake release

On the new image, `sentientosd` reconciles the marker before starting any
maintenance owner. It independently reloads the same pending handoff and N+1,
rechecks exact repository and process launch posture, writes N+1's immutable
per-launch provenance, and writes a v2 readiness receipt. The receipt binds the
configuration, transition, lineage, both generations, continuity receipt,
exact pending event, and N+1 provenance path/digest. The readiness guard
revalidates all those bindings. Only the existing successor owner may then append
`successor_start_attempted`, `successor_confirmed_started`, and
`handoff_completed`; automatic continuity remains a separate complementary
owner and may resume after adoption.

Journal replay accepts only exact phase prefixes for one transition and exact
idempotent immutable evidence. Skips, repeats, branching identities, conflicting
provenance, a second in-flight transition, or completion without the exact
pre-exec transaction fail closed.

STOP prevents a new replacement. A quiescence timeout, stale post-exec readiness
window, lifecycle wall-clock exhaustion, or successful-transition-count
exhaustion prevents further effect. An exec exception is terminal and stale
maintenance remains quiescent. An already-effected transaction may be reconciled
non-effectfully from its exact marker and custody, but recovery cannot authorize
a new exec and does not bypass STOP/pause control over wake effects.

This capability provides no generic service restart, arbitrary process control,
Git mutation, parent supervisor, Windows-native replacement, network/provider
authority, authority widening, expiry extension, or automatic rollback.
