# Sequence 294 — Prove journal-backed recovery after adverse outcomes

Sequence 293 made verified failed or partial outcomes suppress destructive apply. Sequence 294 closes the recovery loop: after a failed `forge_apply`, canonical planning omits that task and records the review requirement; a successful, journal-backed diagnostic review then allows a later canonical plan to reintroduce the task when the existing completion and authority conditions still hold. The review task itself is not misreported as completing the goal.

The regression uses canonical schema-v3 work-run, plan evidence, catalog links, and append-only task journal records. It verifies the later plan against the exact prior run and journal identities. No planning path executes tasks, and all existing explicit execution and apply controls remain required.

The affected local planning, executor, completion, and work-plan suites pass 63/63 with no skips or failures. Compilation and diff checks pass. Hosted exact-source integration, privileged strict audit, immutability, and invariant results are recorded in the sequence evidence after completion.

This recovers the sequence-293 question: successful review can change subsequent planning based on verified journal-backed history, while adverse evidence stays preserved and no authority is inferred from the review result alone.

The verified local source commit is `1b543da87bf4b371cfb37afe6813332f987d92ca`; GitHub published the same tree `6dc3eb0a781f3701d746f79b189947d6bbcbb520` as `11b940fbe2b0ca4f2a557e2f6d1283bce259fa6e`. Hosted CI, the Required Quality Gate, and Invariant Tests all passed on that remote source. The gate artifact confirmed UID 0 Administrator authority, strict audit, immutability, and unchanged exact source.
