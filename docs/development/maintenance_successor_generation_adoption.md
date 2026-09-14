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
incomplete handoff chains, and STOP posture. Absence of N+1 is a zero-effect
`waiting_for_successor` state. It never calls continuity `derive_next`.

Before lifecycle effects, the successor wake closure is canonically validated and
written immutably in generation-specific external custody, then handoff intent is
fsynced. The journal records intent, quiescence request and confirmation, successor
start attempt and confirmation, and completion. The predecessor is stopped only
cooperatively; timeout prevents successor start. A successor start failure does not
restart or roll authority back to N. Completed records reconstruct N+1 and allow the
same posture to adopt an already-derived N+2 without renewed approval.

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
