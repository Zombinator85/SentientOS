# Active construction checkpoint

Sequence 324 binds maintenance-resident child launch provenance to Linux procfs start-time field 22 where available. PID reuse is recoverable only after evidence that the recorded process generation ended. Historical PID-only records remain readable; ambiguous identity remains fail-closed.

Sequence 325 discovered that the strict Quality Gate's generic acceptance selection omitted both sequence 324 task tests. The two recovery nodes and workflow contract assertions were added. Run `39075370096` then caught a shell command-continuation defect: strict audits passed, but the exact-node invocation failed with exit 127 before acceptance or finalization. Sequence 326 repairs command chaining and records that failed attempt. Fresh hosted verification of the 25-node gate remains pending.

Base main for sequence 324: `8a2ab13333574d9112442ef826351596077f267a`, tree `3c0470660da9fd2daeb2a7ffe8b9d83cf82d38c7`. Sequence 326 starts from candidate `3ccc031c55c7889d5ad210186faf30d0bbd08057`, tree `7de5d374c1d54861c5959011a32da35f94db2cf7`.

Prior hosted checks on sequence 324 source passed QG finalization and Docker's 143 tests with 13 skips, but omitted the task-specific nodes. Those runs do not validate this behavior. Sequence 326 requires new exact task-node outcomes, strict Administrator finalization, and all required PR checks.

Sequence 320 records Federation Health scheduled run `39028288072`; sequence 318 records later run `39065143484` on source `b91969c1b1a900fefe102fb72697e7295766857b`. No scheduled execution on current main has been observed. The changed-output publisher fixture is explicit workflow dispatch; no dispatch tool is available here, and an operator request is pending. Nightly audit workflow authority remains read-only in its audit job and repair-scoped for publication, but current-main scheduled evidence remains unverified.

Sequence 286 provenance loss remains unresolved. The stale sequence-178 workspace remains untouched. Production model commissioning and A→B→A evidence still require the exact approved setup.

Latest construction segment: `work/construction/segments/0326-chain-resident-recovery-acceptance-command.md`
Sequence: 326
Segment SHA-256: `a87a6b3ab5bb369ba60124756ee318d7b856519594d84d08bcf8d933278949a7`
