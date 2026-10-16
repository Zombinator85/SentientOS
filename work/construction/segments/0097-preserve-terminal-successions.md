# 0097 — Preserve historical succession links across later generations

Source baseline: `ebe0d33ca7050ae0ab54ee144d426a5d4c65a02a`, tree `4d6c87bd055d45f0c9ecc9794c65cf04e7022cc9`. A three-generation review found that reconciliation reconsidered every unmatched prior claim. Historical claims that already pointed to a direct successor could therefore be rewritten as withdrawn on the next generation, losing the lineage link that explained their historical status.

Reconciliation now carries forward withdrawn claims unchanged and preserves historical claims when they already have a direct successor. Historical evidence that became historical solely because it was stale and unsupported still transitions to withdrawn when absent from the next snapshot. A three-model regression verifies A→B→C retains A→B and B→C separately with their original source attribution.

The focused longitudinal and later-cognition modules passed **34 tests, 0 failed, 0 skipped**. Changed Python files compiled and `git diff --check` passed. Evidence: `work/construction/evidence/0097-multigeneration-self-model-lineage-junit.xml` and `work/construction/evidence/0097-multigeneration-self-model-lineage-results.json`.

This verifies bounded fixture lineage and restart-readable reconciliation records, not model succession or production runtime behavior. Production remains unverified.

Next: examine durable objective-score recovery under partial trial interruption and ensure a fresh owner can distinguish missing conditions from a completed but unscoreable trial without reissuing inference.
