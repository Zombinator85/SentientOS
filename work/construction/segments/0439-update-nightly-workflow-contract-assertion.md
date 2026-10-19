# Sequence 439 — Update the nightly workflow contract assertion

**Construction status: corrective test candidate pending hosted verification.** The first PR #2405 Required Quality Gate (#39217803240) correctly failed closed. Hosted logs isolated one failing contract test: `test_workflow_dispatch_jobs_are_main_bound` still asserted the old repair condition, while sequence 438 intentionally requires both successful completion of the read-only audit job and a nonzero audit finding. The gate finalizer emitted no files after that failed acceptance phase. No workflow-authority assertion or strict audit failed.

Sequence 439 updates the stale test expectation to match the new fail-closed dependency condition. It does not alter workflow source or reduce coverage. The regression continues to pin main-only dispatch, read-only audit/self-check permissions, and the unchanged repair-only write scopes; sequence 438 separately tests both Administrator preflights and ordering. Local compilation, YAML/authority assertions, construction custody, and diff checks pass. The canonical test suite must pass on the updated exact candidate before merge.

Source base: verified main `e66ac2f937db789380ae3da7f2999e4f2a5cd028`, tree `cf063909f5e4f16b22dae09b1ee7cd5a93f09fec`.
