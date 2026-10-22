# Active construction checkpoint

## Current verified state — sequence 586

Sequences 582–586 establish deterministic generation-based epistemic scheduling, test fairness under unequal active evidence, and verify recovery when a state transaction is durable but its mutation receipt publication is interrupted. The controller reconstructs the receipt from exact intent and transaction custody; retry does not duplicate admissions or state advancement. PR #2628's exact candidate passed all eight workflows, including hosted strict audits, finalization, the separate metadata guard, and full CI (143 passed, 13 skipped, zero failed). Its verified tree includes sequence 585's append-only evidence.

Latest verified main: `658e5385d52f8a0adf641106d3a6e852dc8bef25`, tree `11e217ac166ff513a575d789633b457274aa921c`
Latest construction segment: `work/construction/segments/0586-epistemic-receipt-recovery.md`
Latest segment SHA-256: `8e643110e903151ecf187a52a695e5a8d5ebdbfa5ef473842f8fbfc522a4864e`
Sequence: 586 (verified source integration)

Next: exercise the remaining state mutation crash windows, especially a persisted state without its matching update event or admission-bound transaction. Confirm reconstruction fails closed without issuing a receipt or incrementing the service generation, and that conflicting or duplicate transaction evidence cannot be accepted as a recoverable commit.
