# Sequence 269 — Bounded history comparison projection

The cognition projection now preserves historical comparison outcomes while keeping the selected payload bounded. For non-family comparisons it retains top-level classification booleans and compact measurement identity, digest, compared fields, observed difference, and interpretation. Full source payload digests continue to bind the raw history. The family projection remains narrow; no byte limit was increased and no protocol-bound outcome was omitted.

The regression test exercises the same-model identity gate and verifies that positive and adverse comparison outcomes plus measurement identities reach later cognition. The fixture pins one model identity across the compared episodes; production identity and drift checks remain in force.

Validation: the full developmental cognition module and the native focused reporter selection passed (120 collected, 118 passed, 2 skipped, 0 failed). Compilation and `git diff --check` passed. A full repository run remains blocked by unrelated emotion-pump tests that require an admin banner but run unprivileged; the production guard was preserved. No inference, authority expansion, or production action occurred.
