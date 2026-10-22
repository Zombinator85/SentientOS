# Sequence 582 — fair epistemic generation scheduling

Sequence 579's tick-based fairness ordering had a collision edge: the daemon converts the tick timestamp to an integer Unix second, and the owner does not require unique or monotonic ticks. Repeated updates in one second could keep proposition IDs tied and recreate starvation.

PR #2622 changed bounded state scheduling to order pending propositions by durable state generation, least advanced first, then proposition ID. An admitted update increments the generation; owner validation makes that count durable across restart. The selection remains bounded, explicit omitted-proposition reporting remains in place, and all state writes continue through the same admission controller.

The regression initializes two propositions at the same tick, keeps supplying new evidence at that same tick, reconstructs the owner, and verifies the less-advanced proposition receives service while the omitted proposition remains explicit. The exact regression node was selected and passed in hosted source validation.

PR #2622 merged normally as `d28206ce2f87c7a716de252aca5e9dd53085735c`; GitHub confirms main equals the merge commit and its tree `a40da840707418ebd337acdf4825ee9c4876807b` matches the exact candidate. CI passed (143 passed, 13 skipped, zero failed), including source validation, the new regression, self-check, docs, and helm. Required Quality Gate, strict Administrator audits, hosted finalizer, separate metadata guard, Docker, Invariants, Gradient, and Release validation succeeded. All three Lint Benchmark matrix jobs succeeded, although the connector continued to label its top-level workflow summary `in_progress`; this discrepancy is preserved.

No inference or production transition occurred.

Sequence: 582 (verified source integration)