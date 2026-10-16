# Sequence 271 — Isolated planning verification fixtures

The first required hosted workflow on sequence 270 ran both strict audits successfully as UID 0 and bound the verification report to tree `bc378a8eedb8c716a985b228421a8d10e62cc00a`. CI then found a missing repository privilege banner in the new CLI test. A standalone rerun also exposed a test fixture that constructed the daemon planning surface against the host default `/glow` control-plane root.

The test module now has the repository's exact standard banner. The daemon test injects a temporary control-plane kernel, runtime governor root, and host-resource coordinator. It passes in isolation without creating host state. These changes preserve the product gates and behavior.

Validation: the repository privilege linter passed; the focused planning, execution, runtime, hosted-workflow, privileged-wrapper, and mutation-custody suite passed (135 passed, 0 failed); the 17 exact acceptance nodes passed; compilation and targeted CLI mypy passed. The hosted check rerun for this repair is pending publication.
