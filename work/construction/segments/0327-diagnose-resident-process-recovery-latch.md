# Sequence 327: expose process-generation recovery custody failure

## Source and observed failure

This increment starts from sequence 326 candidate `d946460b4411961466576d00f0f381adeb4063d5`, tree `e62cf2c66fa798d2daa38784c48032d4260557cc`.

The repaired Quality Gate command executed all 25 requested nodes in run `39075517162`. The adverse same-generation test passed, but the positive PID-reuse test failed at reconstructed `start()` with `RuntimeError: panic_latched`. Strict audits and import/bootstrap checks passed; acceptance and finalization correctly remained blocked. This proves the required tests are now being executed and surfaced a real test or recovery-state defect.

## Diagnostic change

The positive regression now explicitly parses the persisted receipt journal and validates the persisted parent-state snapshot against the exact child-spec and configuration digests before reconstructing the supervisor. It also asserts that the original and reconstructed supervisor report no panic latch before attempting recovery. The checks preserve fail-closed behavior and make custody-validation failures observable at the point they occur.

## Verification boundary

The diagnostic test change has passed local compilation and `git diff --check`. It is not a behavior fix and does not claim the recovery test passes. A fresh hosted run must identify and resolve the source-caused failure before this increment can be accepted. No panic state is cleared or bypassed.

Sequence 286 provenance loss and the stale sequence-178 workspace remain preserved. No production transition, telemetry, provider use, or new authority is claimed.
