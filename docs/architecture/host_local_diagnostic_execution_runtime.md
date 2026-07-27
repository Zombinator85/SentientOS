# Host-local diagnostic execution runtime

This runtime is the deliberately narrow real-effect consumer of a validated
`host_local_diagnostic_execution_source_runtime.v2` bundle. It performs a
read-only preflight, binds fresh current authorization evidence and an exact
operator confirmation challenge, and permits only one
`diagnostic_write_with_ledger` call through the in-process transaction
orchestrator.

The target directory comes exclusively from the source bundle. The call uses
`force=False`, the fixed diagnostic artifact and ledger names, and never
requests rollback. The six owned files are the diagnostic artifact, effect
receipt, postcondition, production audit, rollback plan, and transaction ledger.
Unrelated siblings are observed and preserved.

A filesystem lock and digest-chained write-ahead states (`prepared`,
`invocation_committed`, `runner_returned`, `observation_persisted`, and
`finalized`) provide durable at-most-once custody. Once invocation is committed,
retry cannot invoke the runner again; it reports completed, partial, or
ambiguous evidence without cleanup or overwrite. Historical bundles embed the
source records and exact target bytes. Live-target comparison is separate and
read-only.

This is a real local diagnostic effect, but reviewer-proof generation never
invokes it. It requires exact v2 source custody, fresh current authority, and
the exact operator challenge. It grants no general filesystem, rollback,
subprocess, shell, network, provider, service, power, thermal, fan/PWM,
hardware, remote, daemon, dashboard, or control-plane authority.
# Custody and recovery hardening

Execution uses one output-root lock from correlation lookup through final pointer
publication.  A durable intent is discovered independently from the final
bundle and carries the legal `prepared`, `invocation_committed`,
`runner_returned`, `observation_persisted`, and `finalized` digest chain.  A
retry never invokes the transaction runner after invocation commitment:
incomplete evidence is reported as partial or ambiguous, while a complete
runner-returned observation may be finalized as reconciled evidence.

The confirmation challenge deterministically binds the source, current grant,
fresh snapshot and verification, execution instant, normalized target, fixed
artifact and ledger paths, and the no-force/no-rollback transaction posture.
Fresh authority is checked during preflight and again immediately before the
invocation commitment.  Final bundles retain source records and target bytes so
historical validation does not depend on either live tree; live-target
validation is a separate read-only comparison.
