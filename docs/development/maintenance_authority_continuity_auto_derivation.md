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
-> canonical maintenance N+1 succeeds and closes
-> the same automatic path derives continuity N+2
-> the same successor owner hands wake ownership to N+2
```

Recovery has precedence over ordinary alignment:

```text
pending auto transaction
-> recover/finalize that exact transaction first
-> then ordinary continuity/adoption alignment
```

The recovery-only reconstruction permits inspection of the exact next receipt/generation
partial pair.  It does not treat either half as current authority; the hardened
`derive_next` verifier alone decides whether the persisted adapters make that half
recoverable.  Ordinary inspection remains strict.  A completed N+1 pair awaiting its
auto receipt is likewise verified against the pending predecessor and evidence before
the receipt and completion event are sealed.

Discovery uses canonical task-journal snapshots and resolves one exact lease,
validation result, commit plan/result, publication request/result chain by native
schema, task identity, and linked digests.  Zero closures waits; the normal
publication-to-close window waits; multiple closures or unexplained repository
advancement blocks.  Missing, malformed, duplicate, or contradictory custody for a
terminal successful claim is broken custody and blocks rather than becoming a normal
wait.  It never uses mtime, newest-name order, inbox content, or caller
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
prevent normalization and derivation.  This includes the watchdog's digest-chained
control-journal pause, not merely its STOP file.  Under that control pause the only
permitted recovery is sealing the receipt/event for an already-effected, exact complete
N+1 pair; it cannot normalize evidence or invoke `derive_next`.

`sentientosd` starts the successor owner first and the complementary auto owner
second; shutdown reverses those two.  Object construction is not startup proof: the
successor owner's `start()` must return true before auto derivation may start.  Auto
derivation is not a cadence owner and is inert unless its exact selected successor
posture is successfully running.

Behavioral proof exercises one persistent policy, successor posture, and automatic
posture through N0→N1 derivation, successor adoption, N1→N2 derivation, and successor
adoption to generation 2.  The test wraps the controller's call boundary to count one
`derive_next` invocation per transition and never uses a manual evidence courier.

```text
canonical successful N0
-> automatic derive N1
-> automatic successor adoption N1
-> canonical successful N1
-> automatic derive N2
-> automatic successor adoption N2
```

There is therefore no normal per-generation human `derive-next` courier in this
authority/configuration loop.  The controller performs no maintenance work, wake
handoff, Git mutation, network/provider activity, process restart, module reload, or
resident-code adoption.  Resident Python may remain older than the repository and
automatic resident Python adoption remains deferred.
