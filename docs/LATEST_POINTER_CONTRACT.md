# Latest Pointer Contract

The latest pointer contract defines one bounded, auditable row per indexed surface.

## Row fields

Each row in `glow/observatory/latest_pointers.json` includes:

- `surface`
- `domain`
- `artifact_type`
- `artifact_path`
- `created_at`
- `run_id`
- `profile`
- `mode`
- `scenario`
- `topology`
- `seed`
- `digest_sha256`
- `pointer_state`
- `freshness_hours`
- `latest_rule`
- `candidate_count`

## Contract guarantees

- deterministic latest pointer selection
- explicit status if no candidates (`missing`)
- explicit staleness policy per surface
- sha256 digest on selected artifact payload
- persisted ordering/selection rule for audit replay

## Provenance links contract

`glow/observatory/artifact_provenance_links.json` captures downstream-to-upstream references.

Current high-value links include:

- fleet observatory summaries → contract/corridor/simulation/formal/WAN/trend artifacts
- WAN gate report → contradiction policy and evidence density artifacts
- WAN gate report → latest WAN truth-oracle summary
- WAN truth-oracle summary → evidence manifest → node truth artifacts
- remote preflight trend report → rollup/history contributing records

## Relationship to source truth artifacts

- Source artifacts remain canonical truth.
- Pointer and link artifacts are locator metadata for operators.
- This layer improves navigation (`summary -> source -> source-of-source`) while preserving immutable source evidence semantics.


## Broad-lane latest pointer contract

Broad lanes now have an explicit contract under `glow/observatory/broad_lane/`:

- `run_tests_latest_pointer.json`
- `mypy_latest_pointer.json`
- `broad_lane_latest_summary.json`

Each lane pointer includes:

- `lane`, `status`, `lane_state`
- `pointer_state` (`current`, `stale`, `missing`, `unavailable`, `incomplete`)
- `primary_artifact_path`
- `supporting_artifact_paths`
- `created_at`
- `run_id`
- `digest_sha256`
- `provenance_resolution` + `why_latest`

`pointer_state` is a recency/completeness signal. `lane_state` remains health/outcome semantics (for example deferred debt vs blocking failure). A lane can be `pointer_state=current` while still `lane_state=lane_completed_with_blocking_failure`.

## Cross-consumer enforcement expectations

Consumers that report broad-lane status should render both `pointer_state` and
`lane_state` in the same row/model and avoid collapsing one into the other.

Common explicit combinations:

- `current + lane_completed_with_advisories` → fresh and healthy.
- `current + lane_completed_with_deferred_debt` → fresh but debt remains.
- `current + lane_completed_with_blocking_failure` → fresh and failing.
- `stale + lane_completed_with_advisories` → last run was healthy but too old.
- `incomplete + lane_incomplete` → attempted run, incomplete evidence.
- `unavailable + lane_unavailable_in_environment` → environment-gated.
- `missing + lane_not_run` → no run evidence.

Out of scope for this pass:

- changing protected-corridor blocking doctrine
- redefining artifact provenance or baseline semantics
- introducing new blocker classes from pointer freshness alone
