# Active construction checkpoint

Last independently verified implementation commit `f3b8e80b1d54ef56fcfadba1fc86b848d9dfa748`, tree `564b197bd26d4c08df25b00f5604ff44fb04b7ec`. Sequence 112 binds invocation generation configuration back to verified receipts and exposes the effective token ceiling in read-only outcome summaries.

Latest segment: `work/construction/segments/0112-bind-effective-generation-ceilings.md`
SHA-256: `0e54a94a2dc3300e05c0f72257632e709c4b86d1a41e55899517e8bba4bc38a2`
Evidence: `work/construction/evidence/0112-bind-effective-generation-ceilings.json`
Evidence SHA-256: `cc33b6ff05b3403f17eed60143bba13f5d16eca49f55a92e55d7f7c659c87ec5`
Sequence: 112

Focused acceptance: 117 passed; 0 failed; 0 skipped. Changed Python compiled. Fixture runs remain synthetic; actual model, backend completion reason, and production are unverified.

Next dependency: determine whether the existing local backend can provide a bounded completion-stop/token observation through authenticated receipt custody without changing historical receipt meaning. Otherwise continue the exact external Windows/CUDA prerequisites and operator handoff; do not treat absent stop metadata or host observation as proof.
