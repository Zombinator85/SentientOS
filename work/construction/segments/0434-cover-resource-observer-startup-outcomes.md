# Sequence 434 — Cover the resource-observer startup outcome matrix

**Construction status: test candidate pending hosted verification.** Sequence 432 extracted the resource-observer selector handling into a testable daemon-startup boundary. Its regression test covered disabled, incomplete, configured-read-only, and missing-bundle behavior. Review found two remaining branches worth binding: a malformed installation identity and a valid selector for an installation that has no state root.

Sequence 434 extends the same focused test to prove malformed identity is rejected before registry access, a missing root is reported as missing without creating it, and a configured existing root still yields a read-only owner that remains unverified until the first tick read. Together the test covers disabled, incomplete, malformed, missing-root, configured-pending-read, and missing-bundle states. No runtime source or authority changes are made.

Source base: verified main `ebe00f30ff38d7d78cab0c18c785ba697bb1d01d`, tree `23ff49b8b812bdc112ad612987beeabf1bfe3968`. Local Python compilation, direct startup-matrix assertions, and `git diff --check` passed. Local canonical pytest remains blocked by the canonical test-install guard; exact-candidate hosted CI, quality gate, and invariant checks are pending.
