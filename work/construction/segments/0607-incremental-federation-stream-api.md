# Sequence 607 — Incremental federation stream API reads

The federation stream endpoint previously reopened and reread the entire JSONL history every second, slicing out bytes after an ever-growing cursor. Its work therefore grew with the total log size on every poll.

PR #2674 changes the endpoint to read at most 64 KiB per poll from a byte offset. It retains only an incomplete line, bounded to 1 MiB, discards oversized and invalid UTF-8 records, and resumes from the start after file truncation or replacement. It emits only complete JSONL records using the existing SSE framing and leaves the endpoint's privilege checks and data source unchanged.

The exact candidate's focused reader regressions passed locally: 9 tests cover bounded reads, complete records, partial-line continuation, oversized-record resynchronization, truncation, replacement, and bounds. The hosted exact-candidate Quality Gate passed strict Administrator audits, the exact 47-node acceptance, reconstructed pre-commit finalization, and the separate metadata guard. The source-validation, self-check, docs, Helm, invariant, lint, build, and CPU-smoke jobs passed.

The first Quality Gate attempt, run #39904424842, correctly stopped at pre-commit metadata validation because it captured the previous PR title. I aligned the title to the exact head commit subject and the fresh exact-candidate gate, run #39904521310, passed its finalizer and separate metadata guard. No source or audit gate was weakened.

The local sandbox's existing TestClient streaming regression hangs even against the pre-change API. A minimal FastAPI StreamingResponse with a finite iterator also hangs in this runtime (FastAPI 0.141.1, Starlette 0.52.1, httpx 0.28.1). The exact candidate's hosted self-check passed, so this local TestClient stall is recorded as an environment limitation, not a successful local integration test or a source failure.

PR #2674 merged normally as `93ed3d0a2c23a8c5c0a6c45600a3643ab90eae5c`, tree `58da62c063b67d1ce692bb68765022de0d1e00f4`, first parent `850b4935ba6a00511749360bdc69e51149f41671`. Every post-merge check on that exact main commit passed, including hosted privileged Quality Gate, source validation, self-check, docs linkcheck, Helm, invariants, builds, CPU smoke, and deploy.

The change bounds the stream consumer's work and buffering. Relay peers are still unauthenticated, and relay output remains separate from Federation Health's local snapshot. A second current-main scheduled health execution has not yet been observed; the latest observed scheduled receipt is run #39902569701, whose report remains stale.

Sequence: 607 (incremental relay-log consumption; no peer authentication, live telemetry, production transition, or goal execution)

