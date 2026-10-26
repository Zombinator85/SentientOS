# Sequence 710: reject non-finite resident adoption bounds

Resident-runtime adoption now rejects NaN, either infinity, and integers too large to convert to finite floats for quiescence timeout, readiness timeout, and wall-clock bounds. The tested code-only tree is `12d2b0f0288211a88f0acac4cdb7dc42e376f394`, based on verified main `974e7c67db914a80ebe01f8cb5598699f3a6b7e0` / `088b42babe3c409d99b0ace8f78f977ae6ebf11d`. All 15 focused regressions passed; 46 other module tests passed. One unrelated environment-provenance test fails identically on the verified base. Targeted mypy reports the same two pre-existing return-type findings on base and candidate; privilege lint, syntax compilation, and diff checks passed.

Evidence record: `work/construction/evidence/0710-reject-nonfinite-resident-adoption-bounds.json`
Evidence SHA-256: `73d72ba3636a0331cf0e9badd1b447002e3fb97f2f88c7db1ce1a8a8ba398882`
