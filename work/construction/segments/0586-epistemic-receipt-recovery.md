# Sequence 586 — verify interrupted epistemic receipt recovery

PR #2628 adds a regression for the boundary between a durable state transaction and publication of its mutation receipt. The test interrupts state-receipt publication after the owner has committed the generation. It confirms no state receipt is visible, then reconstructs the owner and controller. Recovery derives and publishes the receipt only from the exact durable intent and committed transaction, reports verified custody, and the same-tick retry produces no second state receipt or admission. The exact source-validation node passed.

The candidate also includes sequence 585's append-only checkpoint and evidence. Its exact head passed all eight hosted workflows: CI, Required Quality Gate, Lint Benchmark, Codex CI, Gradient, Release, Invariants, and Docker. CI reported 143 passed, 13 skipped, and zero failures. Source validation selected and passed the new receipt-recovery node; strict Administrator audits, audit immutability, hosted finalization, and the separate pre-publication metadata guard passed.

Source head `ebf31c00b9e0d1c42d260ef5f4f038c993feba50` and source-validation checkout `74b3ee66d999f08a6d7c687f45e6fb7931164815` have identical trees. PR #2628 merged normally as `658e5385d52f8a0adf641106d3a6e852dc8bef25`; main matches tree `11e217ac166ff513a575d789633b457274aa921c`. Both changed source and workflow blobs were independently read back byte-for-byte. The sequence 585 evidence was carried in this verified descendant; its standalone evidence PR's CI was still in progress, while the descendant's full exact-candidate check set passed.

No inference or production transition occurred.

Sequence: 586 (verified source integration)
