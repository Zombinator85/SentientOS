# Sequence 699: reject non-finite health wait limits

`WAIT_TIMEOUT=inf` was converted directly to a float, making `end = time.time() + timeout` infinite and the health polling loop unbounded. The CLI and environment default now share finite, non-negative timeout validation. The public polling function also rejects non-finite or negative timeouts and non-finite or non-positive intervals before contacting the endpoint.

The tested code-only tree is `674c04a6c691885344b530cf904cb010edfffdd7`, based on verified main `6c2ea68ffb470ad9add2b0a882fc25a7a65e8dd3` / `382b5c72302ca068432750692fdf969f6195775c`. All 13 focused tests passed, covering CLI values, environment defaults, and direct API limits; targeted mypy, privilege lint for the new test module, syntax compilation, and diff checks passed. Documentation is unchanged. The frozen v1 anchor and prior v2 shards remain unchanged.

Evidence record: `work/construction/evidence/0699-reject-nonfinite-health-wait-limits.json`
Evidence SHA-256: `6f93356d6331e9a1786ca3a84071389db58a6c04aa522f2397e6a74ce495f3d7`
