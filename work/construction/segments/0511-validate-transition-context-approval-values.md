# Sequence 511 — validate transition context approval values

The immutable transition context now rejects values that cannot exist in canonical JSON and mapping keys that are not exact strings. This closes two public-constructor gaps: unsupported mutable leaves can no longer survive recursive freezing, and integer/string keys cannot collapse through string coercion. The regression checks rejection of a mutable bytearray and colliding integer/string mapping keys. Existing nested detachment and authority-boundary checks remain in place.

Supplemental local verification passed 89 affected tests with 0 failures and 0 skips. Targeted Mypy, compileall, CI workflow YAML parsing, diff checks, and append-only construction custody over all 510 predecessors passed. Exact-candidate hosted verification is pending. No production transition, activation, serving, inference, or writeback was performed.

Verified main base: `7fbd149ddb0f48f2385c18590c254a64cc2522bd`, tree `75fc6ab0605f367991e0e3a6e1518d44ea4771e6`
Implementation candidate commit: `1a4c290c3599972d7ac12c2e374d9179a2906dcd`, tree `39d3c649ab4d82275c049d904340612e1a43d1b6`
Sequence: 511 (candidate pending hosted verification)
