# Active construction checkpoint

## Current verified state — sequence 616

Sequences 591–600 establish durable planning and epistemic evidence rules. Sequences 601–606 traced Federation Health's local snapshot boundary and hardened relay parsing and transport framing. Sequences 607–608 implemented bounded incremental SSE log consumption; sequence 609 fixed observed same-inode truncation recovery. Sequences 610–616 integrated evidence to verified main history.

Latest verified main: `aea0feb665e4cd4c0432c7ecae0453e8cf372fab`, tree `c271f173c6b90cdcb6bf2802fdc4cdc588fc1a22`
Latest construction segment: `work/construction/segments/0616-integrate-sequence-615-main-verification.md`
Latest segment SHA-256: 5c6bd227030befe69f9bccfaa3c145e74b670d2e1ad82323b895f17719e5d694
Sequence: 616 (sequence 615 integration and post-merge verification)

The stream API reads fixed-size chunks, emits only complete records, bounds partial-line retention, and resets its cursor after file replacement or an observed in-place size decrease. The relay writes to a separate JSONL path from Federation Health; unauthenticated peer events do not feed the health report.

PR #2686 passed exact-candidate Quality Gate, strict hosted Administrator audit, acceptance binding, hosted landing finalizer, separate metadata guard, CI on PR and push events, Docker, Codex CI, invariants, release, gradient, and lint. The first PR attempt was correctly blocked because its commit subject did not match its PR title; it was closed and the same verified tree passed all gates with matching metadata on PR #2686. Its finalizer artifact digest was independently verified, and the metadata guard bound the exact candidate commit/tree with no reasons. Main's post-merge CI, Quality Gate, Docker, Docs Deploy, Codex CI, and invariants all passed on `aea0feb665e4cd4c0432c7ecae0453e8cf372fab`.

Scheduled Nightly Self Check #39932390030 passed on source `9799837556f67500b3ea517494b76a0785785dad`, including hosted Administrator availability, strict audits, privilege lint, Mypy, airlock, and pytest. Scheduled Nightly Audit Integrity #39927307722 passed its Administrator preflight and strict audit on `d2fe6e729c0e568f11761390a6b4b753df3966be`; no repair was needed.

As of 2026-10-23 09:44:51Z, the latest scheduled Federation Health run remained #39902569701 on older source `7a47004a30d41953436df4266d799b0cbb9d6973`. The App-backed publisher and source-bound execution receipt succeeded, but the report remains a stale configured local-log snapshot, not live telemetry. No schedule-bound run on `aea0feb665e4cd4c0432c7ecae0453e8cf372fab` had appeared.

Next: verify the next real scheduled Federation Health execution against its source SHA and receipt. Keep relay events separate until peer identity, freshness, and revocation are operator-provisioned and verified.
