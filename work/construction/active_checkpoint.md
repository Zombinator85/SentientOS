# Active construction checkpoint

## Current verified state — sequence 621

Sequences 591–600 establish durable planning and epistemic evidence rules. Sequences 601–606 traced Federation Health's local snapshot boundary and hardened relay parsing and transport framing. Sequences 607–608 implemented bounded incremental SSE log consumption; sequence 609 fixed observed same-inode truncation recovery. Sequences 610–620 integrated incremental federation work to verified main history; sequence 619 added operator-pinned federation peer event provenance, and sequence 620 hardened relay JSON handling.

Latest verified main: `db51776cf10752ec74f2c560c9548d448edb7d65`, tree `d26a60e881047912d323cdcf982c6d0e5991460d`
Latest construction segment: `work/construction/segments/0621-integrate-sequence-621-main-verification.md`
Latest segment SHA-256: a04cf54dae90eb06ebbab21d6f0a20bc457956ea94ec3339b7321e769b6f198e
Sequence: 621 (sequence 621 integration and main-source verification)

The stream API reads fixed-size chunks, emits only complete records, bounds partial-line retention, and resets its cursor after file replacement or an observed in-place size decrease. The relay writes to a separate JSONL path from Federation Health; unauthenticated peer events do not feed the health report.

PR #2686 passed exact-candidate Quality Gate, strict hosted Administrator audit, acceptance binding, hosted landing finalizer, separate metadata guard, CI on PR and push events, Docker, Codex CI, invariants, release, gradient, and lint. The first PR attempt was correctly blocked because its commit subject did not match its PR title; it was closed and the same verified tree passed all gates with matching metadata on PR #2686. Its finalizer artifact digest was independently verified, and the metadata guard bound the exact candidate commit/tree with no reasons. Main's post-merge CI, Quality Gate, Docker, Docs Deploy, Codex CI, and invariants all passed on `aea0feb665e4cd4c0432c7ecae0453e8cf372fab`.

Scheduled Nightly Self Check #39932390030 passed on source `9799837556f67500b3ea517494b76a0785785dad`, including hosted Administrator availability, strict audits, privilege lint, Mypy, airlock, and pytest. Scheduled Nightly Audit Integrity #39927307722 passed its Administrator preflight and strict audit on `d2fe6e729c0e568f11761390a6b4b753df3966be`; no repair was needed.

As of 2026-10-23 09:44:51Z, the latest scheduled Federation Health run remained #39902569701 on older source `7a47004a30d41953436df4266d799b0cbb9d6973`. The App-backed publisher and source-bound execution receipt succeeded, but the report remains a stale configured local-log snapshot, not live telemetry. No schedule-bound run on `aea0feb665e4cd4c0432c7ecae0453e8cf372fab` had appeared.

Sequence 616 merged normally through PR #2687 at `aee982295a7f009140420d125c4ff402d6e3562b`, retaining candidate `afa7b577e00f6e5056d5d44733ffa074ab4799af` as the second parent. Exact-candidate gates, the PR and push CI runs, and all post-merge checks passed. The PR self-check's FFmpeg install was slow because the Azure Ubuntu mirror served packages at about 30 kB/s, then APT switched one fetch to `archive.ubuntu.com`; it completed successfully, including demo export.

A real scheduled Federation Health run #39936583192 passed its Administrator preflight, report generation, receipt binding, artifact upload, App token creation, and publication job on then-current main `aea0feb665e4cd4c0432c7ecae0453e8cf372fab`. Its report is a stale local-log snapshot with zero events in the last 24 hours and latest event `2025-06-05T16:25:13.805813Z`, not live telemetry. The App-backed publisher created PR #2688 for the receipt. That PR's base is the earlier main `aea0feb...` and its push self-check remained in the FFmpeg install at the observation cutoff; the PR check itself passed. It must be refreshed and reverified before merging.

As of 2026-10-23 10:24:32Z, no schedule-bound Federation Health execution on current main `aee982295a7f009140420d125c4ff402d6e3562b` had appeared. Main's post-merge CI, Quality Gate, invariants, Docs Deploy, Codex CI, and Docker all passed. The nightly runs remain successful on older source heads; no nightly repair was needed.

Sequence 617 merged normally through PR #2689 at `e4b0161ecebae3ac446da39c2da8a5e6626874b5`, retaining candidate `b6380053a32bcf2421d895ce434f3ca5db33f2ce`. Its exact-candidate gates and all post-merge checks passed, including strict hosted audits, source validation, self-check/pytest, docs, Helm/Kubernetes, and Docker.

As of 2026-10-23 10:36:07Z, the latest scheduled Federation Health run remained #39936583192 on older current-at-run source `aea0feb665e4cd4c0432c7ecae0453e8cf372fab`. There was no schedule-bound run on current main `e4b0161ecebae3ac446da39c2da8a5e6626874b5`. The automated receipt PR #2688 still needs a refreshed source/base and fresh verification.

Next: implement durable ownership of authenticated federation peer replay sequence state. Derive sequence from verified owner history, persist signed-envelope provenance with immutable bounded records, and keep accepted events outside Health, admission, planning, and execution.


Sequence 619 adds a read-only operator-pinned trust catalog and canonical Ed25519 peer-event provenance verification. The verifier binds peer identity, key, endpoint, event digest, validity, revocation, freshness, and the exact next sequence supplied by its caller. It never mutates that caller-owned replay state or admits events to the relay, Health, or execution paths.

PR #2691 merged normally as `428cbce5423cdfc33e4cd1aaabb4740d83b4c901`, retaining candidate `61cc4c7de532a0b167786e14c4006131604cd6a4` as the second parent. The final candidate's hosted QG, CI on PR and push, invariants on PR and push, Docker, lint, release, gradient, Codex CI, and full integrated source validation passed. Its finalizer artifact and separate metadata guard bound the exact candidate/tree with ready decisions and no guard reasons. Earlier module-drift and title-metadata failures were corrected and rerun on the final candidate.

All post-merge checks passed on main `428cbce5423cdfc33e4cd1aaabb4740d83b4c901`, including strict hosted Administrator audits, source validation, self-check/pytest, docs/linkcheck, Helm/Kubernetes, invariants, Docker, and deployment. As of 2026-10-23 11:03:27Z, the next scheduled Federation Health execution on this main had not yet appeared; the latest scheduled report remained a stale local-log snapshot from source `aea0feb665e4cd4c0432c7ecae0453e8cf372fab`.

Sequence 620 integrates strict JSON handling in the Federation SSE relay. PR #2694 merged normally as `fa603571ff392df775b699154df9246e578a0d73`, retaining candidate `baa13f9cc905aed15d4aea379621019c6cddb578`. The final tree is `dd7c6115d59b6f90b556864f6a7c935b9ead4bfc`; the main merge and tested PR merge ref have identical first-parent diffs from `bec349eadbdd18e8a43b4a90f343d90e8f4da0c9`.

The relay rejects duplicate object keys at any nesting level, non-standard non-finite constants, and numeric exponents that overflow to infinity; outbound JSON serialization rejects non-finite values. Its 29-test file is now selected by the canonical source-validation marker filter and bound to exact acceptance. The relay remains outside authenticated event admission, Federation Health, persistence, and execution authority.

The exact candidate Quality Gate passed hosted Administrator audits, its 47-node acceptance, pre-commit reconstruction, hosted finalization, and the separate pre-publication metadata guard. The finalizer artifact independently matched its advertised digest. Fresh PR workflows on the current candidate passed source validation, self-check/pytest, docs, Helm/Kubernetes, Docker, invariants, lint, release, gradient, and Codex CI. The source-validation relay manifest selected all nine declared acceptance nodes; all passed and the verifier returned `task_acceptance_ready` on merge ref `00290bf62ac0d1dc63f37df71dfcc347251cb51a`, whose first-parent diff matches the merged main commit.

At the 2026-10-23 11:55Z verification cutoff, the connected GitHub workflow-run API exposed PR-triggered runs but not the push-triggered post-merge run set; the combined status endpoint returned no status entries for `fa603571ff392df775b699154df9246e578a0d73`. The main commit and source tree were verified, but no post-merge push checks are claimed here. The last Federation Health schedule observation recorded in sequence 619 was run #39936583192 on older source `aea0feb665e4cd4c0432c7ecae0453e8cf372fab`; this session could not query a newer schedule through the available connector.

Next: close the peer replay snapshot filename boundary before adding a durable owner for authenticated peer sequence state. Keep local summary replay distinct from signed-event replay ownership, and keep authenticated events out of Health/admission until that owner and its custody contract are verified.


Sequence 621 integrates PR #2696, which confines local federation replay snapshot filenames, rejects symlinked replay roots and peer files, and validates filename-to-payload identity. Its six-node exact-candidate acceptance and all candidate workflows passed. The change remains isolated from authenticated peer events and Health/admission/execution paths.

Main `db51776cf10752ec74f2c560c9548d448edb7d65` (tree `d26a60e881047912d323cdcf982c6d0e5991460d`) passed post-merge Required Quality Gate, CI, Docs Deploy, Docker, Codex CI, invariants, and Nightly Self Check. The CI source-validation lane completed, including the integrated resource-to-cognition lifecycle and planning/transition checks. The latest scheduled Federation Health report remains run #39936583192 on older source `aea0feb665e4cd4c0432c7ecae0453e8cf372fab`; no schedule-bound execution on current main was observed. Its report is a stale local-log snapshot, not live telemetry. Automated receipt PR #2688 is based on that older source and must be refreshed and reverified.

Next: implement durable ownership of authenticated federation peer replay sequence state. Derive expected sequence from the owner's verified history, persist exact signed-envelope provenance in immutable bounded records, and fail closed when custody or history validation is unavailable. Keep authenticated events out of Health, admission, planning, and execution.
