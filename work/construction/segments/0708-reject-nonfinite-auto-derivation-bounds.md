# Sequence 708: reject non-finite auto-derivation bounds

Continuity auto-derivation now rejects NaN, either infinity, and positive or negative integers too large to convert to finite floats for observation interval and shutdown timeout. The code-only tested tree is `8456dfd682bae883b41a3674a736e5fb062c53f7`, based on verified main `1c9384f37e29bba8a481955c74c68c8760955c6d` / `9b94babbc3e9e4656d6d043e69b9025083e6f2e6`. Ten focused regressions and all 21 tests in the affected module passed; targeted mypy, read-only privilege lint, syntax compilation, and diff checks passed; the documentation build generated 616 pages.

Evidence record: `work/construction/evidence/0708-reject-nonfinite-auto-derivation-bounds.json`
Evidence SHA-256: `9a183f026bcf35aa02f9fe6cd30548b962eae44d226a7e39a85b572900839aee`
