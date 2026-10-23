# Sequence 604 — Bounded federation relay stream framing

Sequence 603 hardened JSON decoding and imposed a 64-KiB limit after an SSE line was delivered by `requests.iter_lines()`. Reviewing the transport path exposed a remaining resource boundary: `iter_lines()` assembles a complete delimiter-free line before the decoder can reject it, so a peer could still cause unbounded buffering.

PR #2667 replaces that iteration with `iter_content(chunk_size=8192)` and an incremental line framer. The framer retains at most the configured 64-KiB line bound, drops oversized lines until their newline delimiter, and then resumes processing later lines. It preserves CRLF handling and the final unterminated line behavior. The existing JSON object validation, source binding, and privilege guards remain unchanged.

The exact source and tests compiled locally and the focused relay suite passed 14 tests, including chunk boundaries, CRLF, final unterminated input, oversized-line discard and recovery, invalid bounds, and invalid chunk types. The tests exercise the pure framing/decoding functions and do not make network requests.

The exact candidate passed the Required Quality Gate with strict Administrator audits, exact acceptance, hosted privileged finalizer, and the separate pre-publication metadata guard. Candidate source validation, self-check, docs link-check, Helm, invariants, lint, build, and CPU smoke checks passed. PR #2667 merged normally as `cd04b9773585de4257baf9391a681142b8ded451`; all post-merge checks on that exact main commit passed, including source validation, self-check, docs, Helm, invariants, build, CPU smoke, Quality Gate, and deploy.

The first evidence-only PR attempt failed the hosted custody guard because the local hash inputs included an extra trailing newline absent from the GitHub blobs. I recalculated the segment and checkpoint bindings over the exact UTF-8 blob contents, corrected the index, and will require a clean custody rerun before merge.

This increment bounds application-level line assembly for each stream chunk, but it does not authenticate peers, establish event freshness, or connect relay output to the Federation Health input. No live telemetry or healthy status is inferred. The latest observed scheduled Federation Health execution remains run 39871453383 on older commit `965659041bc448ba3d3166d7e618ef255abf0387`; the newer successful publisher executions in this construction window were push-triggered.

Sequence: 604 (bounded relay stream framing; no authenticated telemetry, production transition, model inference, or goal execution)
