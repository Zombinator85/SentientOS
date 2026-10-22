# Active construction checkpoint

## Current verified state — sequence 582

Sequence 582 replaces tick-based fairness, which could collide at the daemon's integer-second resolution, with deterministic least-generation-first state scheduling. The same-tick regression passed in hosted source validation after reconstructing the persistent owner. PR #2622 passed strict hosted Quality Gate, CI, source validation, all three lint matrix jobs, and the other required candidate workflows, then merged normally. Main matches its tested source tree. The Lint Benchmark workflow summary lagged its successful matrix jobs and is recorded as a limitation.

Latest verified main: `d28206ce2f87c7a716de252aca5e9dd53085735c`, tree `a40da840707418ebd337acdf4825ee9c4876807b`
Latest construction segment: `work/construction/segments/0582-fair-epistemic-generation-scheduling.md`
Latest segment SHA-256: `2527f1ef23a5b9ed9d4bc69f3a38827866804712daa0473c6c0d073211087d12`
Sequence: 582 (verified source integration)

Next: inspect how least-generation-first behaves when one proposition receives evidence more frequently or has a much larger active binding set. Confirm that the service count advances only after a verified state receipt, that rejected/omitted candidates do not appear served, and that configured proposition limits keep the schedule bounded. Add a targeted regression only if the current lifecycle tests do not already prove these boundaries.
