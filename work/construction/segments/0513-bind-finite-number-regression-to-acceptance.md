# Sequence 513 — bind finite-number regression to acceptance

The first sequence 512 candidate passed its local 92-test suite and Required Quality Gate, but hosted CI correctly rejected its task-acceptance manifest: pytest expanded a parameterized finite-number regression into three node IDs, so the manifest's exact function node was not observed as one successful call. The three rejection cases themselves passed. The regression now exercises NaN and both infinities in one test call, matching the exact source-bound acceptance node without reducing coverage.

The initial CI run `39547010551` failed only at source-validation step `Verify transition-stage receipt projection`; its acceptance result marked the parameterized node unselected. The initial exact-candidate Quality Gate `39547010462`, actual Administrator strict audits, hosted finalization, and separate metadata guard passed. Docker `39547010538`, Release validation `39547010418`, Codex CI `39547010413`, Invariants `39547010516`, Lint Benchmark `39547010526`, and Gradient regression `39547010301` passed. Sequence 512 remains pending until the corrected exact candidate clears the full hosted requirements.

The source follow-up is based on sequence 512's candidate and changes only the exact test node shape. Supplemental local verification passed 90 affected tests with 0 failures and 0 skips; targeted Mypy, compileall, workflow YAML parsing, diff checks, and append-only custody across 512 predecessors passed. No production transition, activation, serving, inference, or writeback was performed.

Verified main: `dd51df9fc0aa21f8ecac732df590716f14d801bb`, tree `2ff89a56f9c8881f7ba66237baf22c5755d6b390`
Acceptance follow-up commit: `f8b627b73234a13d8c1c19659b911e587c0cf1f9`, tree `97fa41a08bf468bf74c86137e74522d223965003`
Sequence: 513 (corrected candidate pending hosted verification)
