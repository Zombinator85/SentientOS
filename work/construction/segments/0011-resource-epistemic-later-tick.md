## 2026-10-12 — continue process/resource observation through epistemic recovery

- Candidate parent: `5648051fcdc5d4b01e64da61c4c236af4f796062`; tree `46354a151bfcbda7c998ddcb65b6ec72070e0b74`.
- Extended the prior real-child process/resource integration through the existing `RuntimeMaintenanceSurfaces.run_epistemic_development` owner with an explicit selector for canonical `causal_resource_consumption` evidence. The resulting binding preserves the ledger receipt event time and does not claim current freshness.
- Reconstructed the persistent epistemic owner and constructed the same mutation controller used at daemon startup; its durable receipt verification is required before the projection boundary accepts mutation-bound state. Tick N projection is omitted; tick N+1 projection is available after recovery. This exercises persisted chronology rather than a process-local flag.
- Combined resource observation, child generation, adapter startup, epistemic development and persistent epistemic-state suites passed 65 tests. Compilation and diff checks passed. Exact details are in `work/resource_invocation_process_generation_acceptance.json`.
- The passing backend is still a controlled fixture. No actual model cognition, improvement, or production behavior is established.
- Next dependency: close the remediation runner's documented crash window between executing an allowed step and publishing its final report. The current owner report can reconcile completed runs, but a crash in that interval leaves no durable attempt marker and must never cause implicit replay.
