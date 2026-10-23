# Sequence 609 — Recover stream cursors after observed in-place truncation

Sequence 608 recorded the direct SSE generator contract and integrated sequence 607's incremental API evidence. Review of that reader found a boundary in truncation detection: if a file was truncated and rewritten between polls, the new file could still be larger than the current cursor while being smaller than the size observed on the previous poll. Checking only the cursor therefore missed the truncation and resumed inside the rewritten file.

The reader now retains the previously observed file size as one bounded state value. A same-inode size decrease resets the byte cursor, pending partial record, and oversize-discard state before reading the next chunk. The 64 KiB read limit, bounded line retention, complete-record framing, file identity checks, and route authority checks are unchanged. A regression rewrites a 100,000-byte file to 80,000 bytes while the cursor is 65,536 bytes and verifies that the new first record is read from the beginning.

The isolated focused suite passed 11 tests on the exact candidate source and test files. The exact-candidate hosted Quality Gate passed strict audits with Administrator authority, acceptance binding, hosted pre-commit finalization, and the separate pre-publication metadata guard. CI, Docker, lint, invariants, release, gradient, and Codex checks also passed. The required CI run's FFmpeg package step took about 27 minutes on one hosted runner and completed successfully; the push-triggered CI run for the same candidate also passed.

Post-merge CI, Quality Gate, Docker, docs deployment, Codex CI, invariants, and nightly self-check all passed on main `9971c16dcc3e184958419f830aff339d645d6f20`, tree `f6201ff99694da8b26f01c36d3ea07acbc3e7fde`. The local TestClient limitation remains unchanged: pre-change streaming behavior and a minimal finite StreamingResponse hang in this sandbox's FastAPI/Starlette/httpx combination; hosted integrated validation passes.

The latest scheduled Federation Health run remains #39902569701 on source `7a47004a30d41953436df4266d799b0cbb9d6973`. The current main does not yet have a scheduled health execution, and the report is still stale rather than live telemetry.

Next, verify the next real scheduled Federation Health execution against its source SHA and publication receipt. Keep federation health separate from unauthenticated relay events until provisioned peer identity, freshness, and revocation rules can be verified.
