# Active construction checkpoint

## Current verified state — sequence 604

Sequences 591–600 establish durable planning and epistemic evidence rules: plans are bound to execution, and stale, foreign, or withdrawn support cannot drive mutation or reactivate after recovery. Sequence 601 traced Federation Health to a tracked local snapshot and found no authenticated bridge from the private relay. Sequence 602 prevents unidentified or sentinel peer rows from inflating health and records a successful push-triggered hosted health execution receipt. Sequence 603 made malformed federation relay SSE payloads fail closed. Sequence 604 bounds transport line assembly before JSON decoding, closing the gap where a delimiter-free peer line could be buffered before the parser's size check.

Latest verified main: `cd04b9773585de4257baf9391a681142b8ded451`, tree `866bf33ced6e3e757a41f330001a605f102b33a2`
Latest construction segment: `work/construction/segments/0604-bounded-federation-relay-stream-framing.md`
Latest segment SHA-256: 61f6bf1c5444a3fbcaa7e5ac1c4b91b2c788ee6e1511a9548d6b43c59f58d5b4
Sequence: 604 (bounded relay stream framing)

Two pre-merge custody attempts found, and the candidate is correcting, stale byte/hash bindings and a checkpoint reference to a prior segment digest. The corrected publication must pass the same guard before merge.

The relay remains unauthenticated and writes `logs/federation_stream.jsonl`, separate from the health report's `logs/federation_log.jsonl`. The size bound applies to retained application-level line data while reading in fixed chunks; do not infer peer trust, event freshness, live telemetry, or health from this relay.

As of this checkpoint, no scheduled Federation Health run on current main has been observed. The latest observed schedule is run 39871453383 on older commit `965659041bc448ba3d3166d7e618ef255abf0387`. Newer successful executions were push-triggered; preserve this event distinction.

Next: continue observing the scheduled health execution and its App publisher receipt. Then define a read-only peer trust catalog and freshness-bound signed event contract only if it can bind to real operator-provisioned peer keys. Keep telemetry fail-closed until the identity and freshness contract is implementable.

