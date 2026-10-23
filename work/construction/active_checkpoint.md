# Active construction checkpoint

## Current verified state — sequence 605

Sequences 591–600 establish durable planning and epistemic evidence rules: plans are bound to execution, and stale, foreign, or withdrawn support cannot drive mutation or reactivate after recovery. Sequence 601 traced Federation Health to a tracked local snapshot and found no authenticated bridge from the private relay. Sequence 602 prevents unidentified or sentinel peer rows from inflating health and records a successful push-triggered hosted health execution receipt. Sequence 603 made malformed relay payloads fail closed; sequence 604 bounded transport line assembly before decoding. Sequence 605 adds an integration regression proving the relay loop uses that bounded stream path and resumes after an oversized line.

Latest verified main: `c4daa4c30c6fa4d45ed7053bb184bba143b381a9`, tree `9c37f416b260ea29b6ebe886a8c839f3e8a870a1`
Latest construction segment: `work/construction/segments/0605-bounded-relay-transport-integration.md`
Latest segment SHA-256: f813bf16e8b3fd95bc43ec4b4019cc56f4177bbc8ff7eb0f8b6bb9c5be633a1d
Sequence: 605 (bounded relay transport integration regression)

The relay remains unauthenticated and writes `logs/federation_stream.jsonl`, separate from the health report's `logs/federation_log.jsonl`. The integration regression is mocked and establishes neither live telemetry nor peer trust.

No scheduled Federation Health run on current main has yet been observed. The latest observed schedule is run 39871453383 on older commit `965659041bc448ba3d3166d7e618ef255abf0387`. Newer successful executions were push-triggered; preserve this event distinction.

Next: observe and verify a scheduled Federation Health execution and its publisher receipt. Then define a read-only peer trust catalog and freshness-bound signed event contract only if it can bind to real operator-provisioned peer keys. Keep telemetry fail-closed until trusted, reachable inputs are verifiable.

