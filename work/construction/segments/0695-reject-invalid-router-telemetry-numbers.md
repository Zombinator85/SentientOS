# Sequence 695: reject invalid router telemetry numbers

The provenance trend analyzer now rejects booleans, non-finite values, and overflowing integers in ordinary run metrics, but router telemetry still called `float(...)` directly. A JSON `true` for `stage_b_evaluations` was counted as one unit of proof spend and `true` for `stage_a_valid_count` was treated as a valid candidate. Non-finite values also contaminated the proof-spend summary.

Router proof-spend and stage-A count metrics now use the same safe numeric conversion as the rest of the analyzer. An always-run regression confirms boolean and non-finite telemetry is normalized to zero and does not become valid proof spend or a valid stage-A candidate.

The tested code-only tree is `e7c80b1315f56ef5183d3c98bd76733c1126be7d`, based on verified main `e7d479a5a7c02957127aba05d2d9f6560a10053f` / `4d1e3874114800829b0ae786d9fc0c61583351cd`. The focused provenance analyzer module passed its two always-run regressions; targeted mypy, syntax compilation, and diff checks passed. Documentation is unchanged. The v1 anchor and all earlier v2 shards remain unchanged.
