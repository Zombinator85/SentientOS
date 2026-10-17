# Active construction checkpoint

Sequence 324 binds each maintenance-resident child launch to Linux procfs process-generation evidence when available. Recovery after PID reuse requires evidence the prior generation ended; ambiguous or still-live identity remains fail-closed. The mypy issue and an intermediate truncated remote source blob were corrected, and the complete source blob was independently read back.

Sequence 325 addresses a hosted verification gap: the strict Quality Gate had not selected the two required sequence 324 recovery tests. The candidate now includes the PID-reuse success case and adverse same-generation case in its exact call-phase selection. Fresh hosted checks for this updated selection are pending.

Exact main base for sequence 324: `8a2ab13333574d9112442ef826351596077f267a`, tree `3c0470660da9fd2daeb2a7ffe8b9d83cf82d38c7`. Sequence 325 starts from candidate `a29f85842b7fdc4495c9e7f12b7d84d76cfa437a`, tree `a36e6438670c2e2722e14f615349d08fc9104ee5`.

Hosted Quality Gate `39074893248` passed its 23 generic nodes, strict Administrator verification, mypy baseline, strict audits, immutability, and landing finalizer. It did not execute the sequence 324 task nodes. Docker `39074893273` passed pre-commit and 143 tests with 13 skips, but provenance likewise showed those nodes were absent. Earlier failed/truncated attempts remain documented in sequence 325 evidence. The updated 25-node gate has not yet run.

Sequence 320 recorded scheduled Federation Health run `39028288072` and verified its artifact; sequence 318 records later scheduled run `39065143484` on source `b91969c1b1a900fefe102fb72697e7295766857b`. No scheduled execution on current main `8a2ab13333574d9112442ef826351596077f267a` has been observed. The changed-output fixture remains an explicit `workflow_dispatch`; the available GitHub connection has no dispatch action. Nightly strict-audit source retains read-only audit permission and write authority only for repair publication, but current-main scheduled execution remains unverified.

Sequence 286 provenance loss remains unresolved. The stale sequence-178 workspace remains untouched. Production model commissioning and temporal A→B→A evidence remain pending the exact operator-approved setup.

Latest construction segment: `work/construction/segments/0325-execute-resident-recovery-acceptance-in-hosted-gate.md`
Sequence: 325
Segment SHA-256: `596b3c5ab6246172d51c4574a9eeaa2ec4e41f2bea3c010a8f4fe19b569ddbcf`
