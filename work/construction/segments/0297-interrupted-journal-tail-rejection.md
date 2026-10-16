# Sequence 297 — Preserve interrupted journal tails and reject same-size drift

Sequence 297 adds two regression cases for the bounded work-plan journal. A writer whose recovered journal is changed without changing its byte length now has an explicit rejection test, and a truncated final record is rejected while the exact interrupted bytes remain untouched. These cases preserve the fail-closed behavior: recovery does not repair or discard an incomplete append.

The focused journal, executor, and planner suites pass 39/39 with no skips or failures. Compilation, Mypy for the changed test module, construction custody, and diff checks pass; custody verifies all 296 predecessor segments.

The verified local source candidate is `7cb74e9849e9f236e9ccec7d575cbb68e75b676a`; GitHub published the exact tree `3db7e4a1981a36716b8f56c988d48ca841b998e5` as `0b71e1826bf8cb68269c4ee5930f5c3e7cb608ff`. CI `38983181075`, Required Quality Gate `38983181073`, and Invariant Tests `38983181083` all passed on that exact remote SHA. The gate artifact `12081932247` was independently downloaded; its ZIP digest matched GitHub's `78f16057c770c6588f9c11889df72df7d7a5b7475621ad00076eaaa672a79f6a`. Its report confirms effective UID 0, actual Administrator authority, exact source/tree binding, unchanged source and repository identity, successful strict audit, and successful immutability verification.

The sequence-286 historical provenance limitation remains explicit: nine known deleted payloads and one unidentified deleted payload are unrecoverable. No historical payload was reconstructed or omitted from the claim.

Next dependency: verify that competing journal writers in separate processes serialize through the kernel lock and cannot fork the append-only hash chain.
