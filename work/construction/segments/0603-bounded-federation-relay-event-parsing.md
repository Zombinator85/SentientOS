# Sequence 603 — Bounded federation relay event parsing

The existing federation stream relay expected every valid JSON SSE payload to be an object. For a valid JSON array, scalar, or `null`, it attempted to assign `data["source"]`; that raised outside the decode exception handler and ended that peer's relay thread. Deeply nested JSON and very large integer tokens could also raise parser exceptions.

PR #2665 extracted a focused SSE event decoder. It ignores non-data lines, payloads over 64 KiB, malformed or non-UTF-8 JSON, non-object values, excessive nesting, and integer-limit parse failures before JSON serialization or persistence. Accepted objects retain their data and receive the configured source URL as before. The privileged entrypoint's Administrator and LUMOS guards are unchanged.

The focused local suite passed 11 tests against the exact candidate files. The preserved auxiliary environment lacks the `requests` package, so those pure-decoder tests inject an inert `requests` module and make no network calls. The hosted exact-candidate checks provide environment verification. The size limit is applied after `requests.iter_lines()` has yielded a line; it does not claim to bound transport buffering.

The first hosted Quality Gate attempt failed during pre-commit reconstruction because repository governance requires the PR title to equal the latest commit subject. The candidate's title still reflected its earlier fix commit after a follow-up test commit was added. I changed the PR title to the exact latest commit subject and reran the gate. The rerun passed strict Administrator audits, exact acceptance, hosted finalizer, and the separate metadata guard; the full candidate checks passed.

PR #2665 merged normally as `f833f9dd131d0da19635ef13cbbd4128371ff095`, tree `c1183e45afed5f81f33233477e45bce8cbcf3ead`, first parent main `964916158558ac6dde3ec084d0350bbf0d972fc6`. The post-merge Quality Gate, source validation, self-check, strict docs, Helm, invariants, build, CPU smoke, and deploy checks passed. Nightly Self Check also passed on the merged main SHA via its push trigger.

This increment only makes malformed relay records fail closed at the decoder. Peer traffic is still unauthenticated, freshness is not established, and the relay still writes a different file than the Federation Health report reads. No live telemetry or healthy status was inferred. The latest observed scheduled Federation Health run remains 39871453383 on older commit `965659041bc448ba3d3166d7e618ef255abf0387`; the successful run on newer main was push-triggered.

Sequence: 603 (bounded relay parser and fault containment; no authenticated telemetry, production transition, model inference, or goal execution)
