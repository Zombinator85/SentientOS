# Sequence 623 — integrate local semantic review and repair Ubuntu mirror fallback

Sequence 623 adds a locally pinned semantic review boundary for authenticated Federation peer events. The policy permits only exact peer/schema pairs for bounded claim-evidence and trial-outcome shapes. Its receipt binds the replay-record digest, event digest, trust-catalog identity, and local policy digest; preserves positive, adverse, mixed, and inconclusive outcomes; and permits only local review eligibility. Remote references remain unresolved, remote labels remain submitter assertions, and the receipt explicitly denies canonical evidence admission, Health publication, work admission, planning, execution, and decision power.

PR #2701 candidate `10767a8e9b411d76a3ef6273ef5b0847c4d30bf0` (tree `eff0790235ae33716c0094a78d1354e5df1e79c6`) merged normally as `86d1471f01a26786b61cc7a5df6b957e8e21551c` (tree `eff0790235ae33716c0094a78d1354e5df1e79c6`), retaining the candidate as its second parent. The merge commit is GitHub-verified and its first parent is `72fbb3f18ee884e82946846ecba7002d17001ce4`.

The candidate also repairs the CI failure observed while installing FFmpeg on GitHub-hosted Ubuntu. The failing runner resolved Azure through `/etc/apt/apt-mirrors.txt`; rewriting only ordinary APT source files left that mirror active. The corrected fallback rewrites and verifies the mirror-list file and ordinary source files, fails if it cannot establish the public archive, refreshes package indexes, then retries the required install. On the slow push-triggered self-check, the log confirmed package downloads from `archive.ubuntu.com`, successful FFmpeg installation, and successful parliament demo generation.

## Candidate verification

The exact-candidate Required Quality Gate #39969509113 passed strict hosted Administrator audits, exact acceptance binding, hosted finalization, and the separate pre-publication metadata guard with status `pr_metadata_guard_ready` and no reasons. Its finalizer artifact is #12508805892 (`sha256:809e184035b02b1b3a6a114eaab2e97bec0b694d9e1fee8ed8e4910e4ba5a786`); exact acceptance artifact #12508377115 (`sha256:b1ebc50783db956c4b83c864156822dae7c9b7a96cca8b286feec154711bbb82`); quality-gate evidence #12508562001 (`sha256:0661eda3183a76aa863bdbb97c3ddabc097570569fcfaf04995b64d9bbc25898`).

PR and push CI runs #39969399267 and #39969392201 passed, including source validation, semantic replay tests, workflow fallback regression, full self-check, documentation, and Helm/Kubernetes. The push self-check log confirms public-archive package downloads and the parliament demo. Invariants passed on PR #39969399729 and push #39969392239; Docker #39969399274, Codex CI #39969399477, lint #39969399632, release validation #39969399620, and gradient regression #39969399528 passed.

Two earlier failures were resolved before landing. The first mirror-fallback implementation did not edit the runner's apt mirror-list file; this was corrected and exercised on the slow runner. A Quality Gate run #39969399295 used a stale PR-title event snapshot and failed the metadata match; the PR metadata was aligned with the final commit and the later exact-candidate gate passed. No check was waived.

## Post-merge verification

On exact main `86d1471f01a26786b61cc7a5df6b957e8e21551c`, Required Quality Gate #39970370432, CI #39970370691, Nightly Self Check #39970370429, Docs Deploy #39970370591, Docker #39970370620, Codex CI #39970370435, and Invariant Tests #39970370487 all passed. CI's source-validation job #120471130654, self-check #120471130194, documentation job #120471130217, and Helm job #120471129723 all passed. The integrated resource-to-cognition lifecycle and read-only campaign-report checks passed within source validation. Forge Smoke #39970370893 was skipped by its workflow condition.

As of 2026-10-23 14:36 UTC, the latest scheduled Federation Health run remained #39936583192 on the older source `aea0feb665e4cd4c0432c7ecae0453e8cf372fab`. No schedule-bound post-merge execution had appeared. Its report remains a configured local-log snapshot rather than live telemetry; it is not evidence for the newly merged source.

Next: make semantic-review receipts canonical and independently revalidatable before persisting them in a local review docket. Keep replay/signature provenance separate from semantic eligibility, keep remote references unresolved, and preserve the existing explicit denials on Health, evidence admission, work admission, planning, and execution.

This segment is append-only and follows `segment-sha256:544de0e40b938ec6519a1cc3a5595dcd3938d36472733f9f7ff1846fa652e07e`.
