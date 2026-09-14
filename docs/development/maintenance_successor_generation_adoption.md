# Maintenance successor-generation adoption

The `sentientos.maintenance_successor_generation_adoption_config:v1` document is
the operator's persistent, digest-bound decision to follow one exact continuity
lineage. It binds the policy, generation zero, initial wake adoption, repository,
private state/output roots, handoff journal, STOP marker, and all lifetime and
shutdown bounds. Current authority is never a mutable pointer: it is generation
zero plus the validated sequence of completed handoff receipts.

The controller observes only the canonical `generation-(N+1).json` and
`receipt-(N+1).json`. It rejects skips, lineage/predecessor/digest disagreement,
non-canonical receipts, widened authority evidence, output conflicts, corrupt or
invalid handoff chains, and STOP posture. Absence of N+1 is a zero-effect
`waiting_for_successor` state. It never calls continuity `derive_next`.

## Production configuration closure

`build_successor_adoption` is the default builder installed by
`MaintenanceSuccessorGenerationOwner`; `sentientosd` therefore needs no callback
or test-only dependency injection. It verifies the generation-bound activation
manifest and rendered profile bundle, then derives the existing watchdog,
candidate-collector, autonomy-cycle, health-probe, wake-cycle, and wake-daemon
schemas from the predecessor closure. Only successor bindings and private,
generation-specific state/configuration paths are rebound. Every `base_sha` is the
successor base, watchdog/profile/collector/autonomy references agree, and each
native validator plus the wake doctor runs before quiescence. Writes are exclusive
and deterministic: equal bytes are reused and unequal existing bytes block.

Cadence custody is not shared across adoption digests. The successor receives a
new generation-specific cadence root and uses the predecessor journal's canonical
`next_due_utc` as its immediate-posture anchor. Thus an already-due instant remains
due, a future instant remains future, missed intervals are still collapsed by the
wake daemon's native next-due rule, and creation of a new adoption does not reset
the schedule.

Before lifecycle effects, the successor wake closure is canonically validated and
written immutably in generation-specific external custody, then handoff intent is
fsynced. The journal records intent, quiescence request and confirmation, successor
start attempt and confirmation, and completion. The predecessor is stopped only
cooperatively; timeout prevents successor start. A successor start failure does not
restart or roll authority back to N. Completed records reconstruct N+1 and allow the
same posture to adopt an already-derived N+2 without renewed approval.

## Replay and bounded recovery

Replay accepts exact six-phase historical transactions and at most one final exact
phase prefix. It reconstructs authority only from `handoff_completed`; an intent
never advances the current generation. A prefix through intent or quiescence
request can move forward only after the predecessor owner lock is provably free and
the predecessor cadence journal has no unmatched invocation intent. A durable
quiescence confirmation proceeds forward without restarting N. A start-attempt
prefix is retried only when the successor lock proves startup did not remain active;
a busy lock is ambiguous and blocks. After durable start confirmation, the exact
same adoption is reconstructed under its lock before completion is appended.

Corrupt ordering, gaps, duplicate phases, changed transaction identity, competing
owners, unmatched wake intent, and custody that cannot distinguish an active owner
remain intentionally fail closed. Owner-loop configuration, integrity, and custody
exceptions are caught at the lifetime boundary, projected as terminal degraded
health, and stop further effects; cooperative bounded `stop()` remains available.

`SENTIENTOS_MAINTENANCE_SUCCESSOR_GENERATION_ADOPTION_CONFIG` selects this owner in
`sentientosd`. Scheduler, direct wake, and successor-generation owners are mutually
exclusive; overlap starts none. Without this variable, direct wake behavior is
unchanged.

Implemented:

```text
verified N+1 already exists
-> automatically prepare successor configs
-> quiesce N
-> adopt N+1 wake owner
-> continue cadence under N+1
```

Still deferred:

```text
successful N closes
-> automatically invoke continuity derive-next
```

```text
repository contains N+1 Python
-> automatically make N+1 Python resident in sentientosd
```

Wake/configuration adoption does **not** restart, exec, reload, or hot-load Python.
The long-running process can therefore still execute generation-N resident code.
