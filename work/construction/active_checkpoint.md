# Active construction checkpoint

## Current verified state — sequence 618

Sequences 591–600 establish durable planning and epistemic evidence rules. Sequences 601–606 traced Federation Health's local snapshot boundary and hardened relay parsing and transport framing. Sequences 607–608 implemented bounded incremental SSE log consumption; sequence 609 fixed observed same-inode truncation recovery. Sequences 610–618 integrated evidence to verified main history.

Latest verified main: `e4b0161ecebae3ac446da39c2da8a5e6626874b5`, tree `66c9daa1d2063734de6af652cf14158e5e18181b`
Latest construction segment: `work/construction/segments/0618-integrate-sequence-617-main-verification.md`
Latest segment SHA-256: 06fc7ac815c6d3128e244b7d37c084892c5dc417a0ae36d19912b766c1827cbb
Sequence: 618 (sequence 617 integration and post-merge verification)

The stream API reads fixed-size chunks, emits only complete records, bounds partial-line retention, and resets its cursor after file replacement or an observed in-place size decrease. The relay writes to a separate JSONL path from Federation Health; unauthenticated peer events do not feed the health report.

PR #2686 passed exact-candidate Quality Gate, strict hosted Administrator audit, acceptance binding, hosted landing finalizer, separate metadata guard, CI on PR and push events, Docker, Codex CI, invariants, release, gradient, and lint. The first PR attempt was correctly blocked because its commit subject did not match its PR title; it was closed and the same verified tree passed all gates with matching metadata on PR #2686. Its finalizer artifact digest was independently verified, and the metadata guard bound the exact candidate commit/tree with no reasons. Main's post-merge CI, Quality Gate, Docker, Docs Deploy, Codex CI, and invariants all passed on `aea0feb665e4cd4c0432c7ecae0453e8cf372fab`.

Scheduled Nightly Self Check #39932390030 passed on source `9799837556f67500b3ea517494b76a0785785dad`, including hosted Administrator availability, strict audits, privilege lint, Mypy, airlock, and pytest. Scheduled Nightly Audit Integrity #39927307722 passed its Administrator preflight and strict audit on `d2fe6e729c0e568f11761390a6b4b753df3966be`; no repair was needed.

As of 2026-10-23 09:44:51Z, the latest scheduled Federation Health run remained #39902569701 on older source `7a47004a30d41953436df4266d799b0cbb9d6973`. The App-backed publisher and source-bound execution receipt succeeded, but the report remains a stale configured local-log snapshot, not live telemetry. No schedule-bound run on `aea0feb665e4cd4c0432c7ecae0453e8cf372fab` had appeared.

Sequence 616 merged normally through PR #2687 at `aee982295a7f009140420d125c4ff402d6e3562b`, retaining candidate `afa7b577e00f6e5056d5d44733ffa074ab4799af` as the second parent. Exact-candidate gates, the PR and push CI runs, and all post-merge checks passed. The PR self-check's FFmpeg install was slow because the Azure Ubuntu mirror served packages at about 30 kB/s, then APT switched one fetch to `archive.ubuntu.com`; it completed successfully, including demo export.

A real scheduled Federation Health run #39936583192 passed its Administrator preflight, report generation, receipt binding, artifact upload, App token creation, and publication job on then-current main `aea0feb665e4cd4c0432c7ecae0453e8cf372fab`. Its report is a stale local-log snapshot with zero events in the last 24 hours and latest event `2025-06-05T16:25:13.805813Z`, not live telemetry. The App-backed publisher created PR #2688 for the receipt. That PR's base is the earlier main `aea0feb...` and its push self-check remained in the FFmpeg install at the observation cutoff; the PR check itself passed. It must be refreshed and reverified before merging.

As of 2026-10-23 10:24:32Z, no schedule-bound Federation Health execution on current main `aee982295a7f009140420d125c4ff402d6e3562b` had appeared. Main's post-merge CI, Quality Gate, invariants, Docs Deploy, Codex CI, and Docker all passed. The nightly runs remain successful on older source heads; no nightly repair was needed.

Sequence 617 merged normally through PR #2689 at `e4b0161ecebae3ac446da39c2da8a5e6626874b5`, retaining candidate `b6380053a32bcf2421d895ce434f3ca5db33f2ce`. Its exact-candidate gates and all post-merge checks passed, including strict hosted audits, source validation, self-check/pytest, docs, Helm/Kubernetes, and Docker.

As of 2026-10-23 10:36:07Z, the latest scheduled Federation Health run remained #39936583192 on older current-at-run source `aea0feb665e4cd4c0432c7ecae0453e8cf372fab`. There was no schedule-bound run on current main `e4b0161ecebae3ac446da39c2da8a5e6626874b5`. The automated receipt PR #2688 still needs a refreshed source/base and fresh verification.

Next: verify the next actual scheduled Federation Health execution against current main and refresh the publisher receipt PR. Continue the operator-provisioned federation peer identity, signature, freshness, and revocation dependency while keeping unauthenticated relay events isolated from Health.
