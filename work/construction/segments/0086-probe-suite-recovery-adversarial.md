# 0086 — Reject probe-suite identity and receipt substitution

Source baseline: `6a8502675074eb9c116ded9b0d36eab67495c1f6`, tree `0e220c690112b654c0e9dd42f779f6d5edb39c41`. Added suite-specific tampered-plan and answer/output-digest substitution controls. Altered oracle plan parameters are rejected against the originally verified plan without additional endpoint calls. When returned answer bytes do not match the invocation's output digest, the run is classified contradictory, and reconstruction returns that result without replaying inference.

Focused objective-scoring module: **22 passed, 0 failed, 0 skipped**. Changed Python compiled and `git diff --check` passed. Evidence: `work/construction/evidence/0086-probe-suite-recovery-adversarial-junit.xml`, `work/construction/evidence/0086-probe-suite-recovery-adversarial-results.json`.

Hosted checks for seq85 were captured at `work/construction/evidence/0086-hosted-checks-seq85.json`: Source Validation succeeded; the invariant job exited during collection at the existing administrator gate in `prompt_assembler`; the docs builder also requires administrator/Lumos approval; self-check failed on `/glow` permissions, package import and protected Forge CI authorization. Helm was still in progress at capture time. No privilege boundary was weakened.

Next: query the terminal Helm outcome for seq85 and continue toward an exact, authorized local-model trial only if required payload and commissioning evidence become available. Otherwise move to another independently implementable downstream developmental integration; do not infer loaded-code identity or real-model performance.
