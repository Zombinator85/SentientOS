# Automatic maintenance authority continuity derivation

The implemented controller binds one immutable
`sentientos.maintenance_authority_continuity_auto_derivation_config:v1` to the exact
continuity policy and enabled successor-adoption configuration.  It reconstructs the
adopted generation from generation zero plus completed handoff events; a higher file
on disk is never adoption authority.  The adopted wake document leads through its
wake and autonomy configurations to the exact watchdog configuration and task state
root.

The recurring configuration-authority chain is:

```text
adopted N
-> canonical maintenance N succeeds
-> exact local absorption
-> terminal closure
-> auto discovery
-> v2 normalization
-> hardened derive_next
-> continuity N+1
-> existing successor-adoption owner sees N+1
-> handoff to wake generation N+1
```

Discovery uses canonical task-journal snapshots and resolves one exact lease,
validation result, commit plan/result, publication request/result chain by native
schema, task identity, and linked digests.  Zero closures waits; the normal
publication-to-close window waits; multiple closures or unexplained repository
advancement blocks.  It never uses mtime, newest-name order, inbox content, or caller
selection.

The normalized schemas remain
`sentientos.completed_maintenance_generation_evidence:v2` and
`sentientos.exact_successor_repository_evidence:v2`.  Their immutable paths are
`<evidence-root>/generation-NNNNNN/<task-id>/completion-v2.json` and
`successor-v2.json`.  The intent event durably fixes `evaluation_time` before these
writes, so exact retries reuse `observed_at` and equal bytes.  The digest-chained
`sentientos.maintenance_authority_continuity_auto_derivation_event:v1` phases are
transition intent, evidence normalization, derivation intent, and completion.  The
final immutable receipt is
`sentientos.maintenance_authority_continuity_auto_derivation_receipt:v1`.

Continuity derivation is serialized per lineage and can complete only an exactly
reconstructed missing receipt or generation half.  Conflicts remain blocked.  One
iteration derives at most N→N+1, then reports `waiting_for_successor_adoption` until
the independent handoff owner advances adopted custody.  STOP markers on the auto
posture, successor posture, current wake posture, or current watchdog pause all
prevent normalization and derivation.

`sentientosd` starts the successor owner first and the complementary auto owner
second; shutdown reverses those two.  Auto derivation is not a cadence owner and is
inert unless its exact selected successor posture is running.

There is therefore no normal per-generation human `derive-next` courier in this
authority/configuration loop.  The controller performs no maintenance work, wake
handoff, Git mutation, network/provider activity, process restart, module reload, or
resident-code adoption.  Resident Python may remain older than the repository and
automatic resident Python adoption remains deferred.
