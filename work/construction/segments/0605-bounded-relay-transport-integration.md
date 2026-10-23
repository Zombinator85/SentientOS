# Sequence 605 — Exercise bounded relay transport integration

Sequence 604 bounded SSE line assembly using fixed-size streamed response chunks and a 64-KiB maximum retained line. Its focused tests exercised the framer directly, but did not prove that the production relay loop actually called the bounded streaming path.

PR #2669 adds a mocked-response regression for `relay_peer()`. The test asserts that the relay requests `iter_content(chunk_size=8192)`, discards an oversized event, resumes after the next newline, and persists the following valid event with its configured source URL. It uses no network connection and does not change runtime behavior.

The exact candidate compiled and its focused relay suite passed 15 tests locally. Hosted exact-candidate checks passed the required Quality Gate, strict Administrator audits, exact acceptance, privileged finalizer, independent metadata guard, source validation, self-check, docs, Helm, invariants, lint, build, and CPU smoke. PR #2669 merged normally as `c4daa4c30c6fa4d45ed7053bb184bba143b381a`, tree `9c37f416b260ea29b6ebe886a8c839f3e8a870a1`, first parent main `c1db6855ccc3920ea4cafaa2fe9d25bb09fb5724`.

This is integration-test coverage only. It does not exercise live peer traffic, authenticate a peer, establish freshness, or connect relay output to Federation Health. No live telemetry or healthy status is inferred. The latest observed scheduled Federation Health run remains 39871453383 on older commit `965659041bc448ba3d3166d7e618ef255abf0387`; successful newer-main executions remain push-triggered.

Sequence: 605 (bounded relay stream integration regression; no live telemetry, production transition, model inference, or goal execution)
