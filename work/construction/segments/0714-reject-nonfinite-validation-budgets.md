# Sequence 714: reject non-finite validation budgets

The shared validation budget normalizer now converts overflow, NaN, infinities, and negative values into its documented `invalid_budget_or_duration` error while preserving finite nonnegative budgets. The tested code-only tree is `01e9200db8f3c3302b5b564a9d1d92bcfe50bf5c`, based on verified main `81dbdf4dbd85011a9fb42729ea6db7f8bc88f715` / `fa1cd6ff980143840792a0b7a50d17a8c797ddaf`. All five focused regressions and all ten planner tests passed. Targeted mypy has the same six baseline return-type findings on both base and candidate; privilege lint, syntax compilation, and diff checks passed.

Evidence record: `work/construction/evidence/0714-reject-nonfinite-validation-budgets.json`
Evidence SHA-256: `55317b096fd822b0d8a1c4364f895098f6ca4deefd66642d8d5d0bbec8752561`
