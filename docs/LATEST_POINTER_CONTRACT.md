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

