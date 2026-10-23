# Sequence 611 — Integrate sequence 610 and verify main

Sequence 610 reconciled sequence 609's recovery evidence to main. Its evidence PR #2680 merged normally at `1cb46340663931866f7a73ec19c88415f2b51583`, with `f46dd7a2dfcfe51ab253889520db647b8098a9c2` as first parent and candidate `18196e350a7e918c6697755d9155b3fee2a28e28` preserved as second parent. Main’s tree is `b070b614eb075b5926541c67a6c6be5a571a3336`; the active construction index and checkpoint are bound to sequence 610.

All exact-candidate checks for PR #2680 passed: Required Quality Gate with strict Administrator audits, exact acceptance, hosted landing finalization, and the separate pre-publication metadata guard; CI, Docker, Codex CI, invariants, release, gradient, and lint passed. Main’s post-merge CI, Quality Gate, Docker, Docs Deploy, Codex CI, and Invariant Tests also passed. The initial main Docker attempt failed while pushing to GHCR with `unknown blob` after build and tests succeeded. GitHub’s failed-job retry succeeded on attempt 2; no build or test change was made.

As of 2026-10-23T07:39:47Z, the latest scheduled Federation Health run remained #39902569701 on older source `7a47004a30d41953436df4266d799b0cbb9d6973`. Its report artifact digest and receipt-bound report SHA were independently checked; publisher PR #2672 was created and merged. The report remains a stale configured local-log snapshot, not live telemetry: zero events in 24 hours, with the last recorded event at 2025-06-05T16:25:13.805813Z. No scheduled run bound to `1cb46340663931866f7a73ec19c88415f2b51583` had appeared by the cutoff.

The latest scheduled Nightly Audit Integrity and Nightly Self Check executions remained successful on 2026-10-22 and older source `7d55b9757a10322d680f6fb450691de7ff7f8506`. Neither workflow had a new scheduled execution on sequence 610 main by the cutoff. Their privileged preflights and repair scope remain unchanged.

Next, verify actual scheduled Federation Health and nightly executions against their exact source SHAs and receipts. Keep the health snapshot separate from unauthenticated relay events until provisioned peer identity, freshness, and revocation contracts are in place.
