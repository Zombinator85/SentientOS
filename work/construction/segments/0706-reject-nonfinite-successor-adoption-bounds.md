# Sequence 706: reject non-finite successor adoption bounds

Successor-generation adoption now rejects NaN, infinities, and numeric bounds too large to convert to finite floats for observation delay and shutdown timeout. The tested code-only tree is `2e1a3be22c43cf81f2ba14ca61c3087632261163`, based on verified main `dea80feb2c6ec548eb39518d5190002f9a23edc8` / `c5aa9f3ce166f4b7d55608ae00f8c869f68e990b`. All eight focused regressions passed; targeted mypy, privilege lint, syntax compilation, and diff checks passed.

Evidence record: `work/construction/evidence/0706-reject-nonfinite-successor-adoption-bounds.json`
Evidence SHA-256: `9b0c2447cdfd737325f9727e6ab4bbb285614af94875c4afbc6099e9f122c06f`
