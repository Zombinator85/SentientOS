# Active construction checkpoint

## Current verified state — sequence 603

Sequences 591–600 establish durable planning and epistemic evidence rules: plans are bound to execution, and stale, foreign, or withdrawn support cannot drive mutation or reactivate after recovery. Sequence 601 traced Federation Health to a tracked local snapshot and found no authenticated bridge from the private relay. Sequence 602 prevents unidentified or sentinel peer rows from inflating health and records a successful push-triggered hosted health execution receipt. Sequence 603 makes malformed federation relay SSE payloads fail closed before persistence, while leaving peer authentication, event freshness, and health-input integration unresolved.

Latest verified main: `f833f9dd131d0da19635ef13cbbd4128371ff095`, tree `c1183e45afed5f81f33233477e45bce8cbcf3ead`
Latest construction segment: `work/construction/segments/0603-bounded-federation-relay-event-parsing.md`
Latest segment SHA-256: `1e2004a996f7f38bd1a59251bee56261425136baedb2469144290c0a1715ed35`
Sequence: 603 (verified relay parser fault containment)

The 64-KiB event check applies after the HTTP library yields a line; it does not bound transport buffering. The relay remains unauthenticated and writes `logs/federation_stream.jsonl`, separate from the health report's `logs/federation_log.jsonl`. Do not infer freshness, live health, or peer identity from the configured source URL.

A successful post-merge Federation Health execution and App receipt publication are recorded in sequence 602, but that run was push-triggered. As of this checkpoint no fresh scheduled Federation Health run on the new main has been observed; the latest observed scheduled run is still 39871453383 on older commit `965659041bc448ba3d3166d7e618ef255abf0387`. Continue to keep scheduled evidence distinct from push-triggered execution.

Next: investigate the missing scheduled execution, then define a read-only trust catalog and freshness-bound signed event contract only if it can bind to real operator-provisioned peer keys. Preserve fail-closed behavior until trusted, reachable inputs can be verified.
