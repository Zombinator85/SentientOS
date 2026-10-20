# Sequence 483 — Expose prior-projection omission count

## Source increment

PR #2469 makes the verified prior cognitive projection's omitted-state count visible in allocation decisions and daemon planning feedback. It reads the count from the validated projection omission manifest and leaves the field null when no prior projection or no manifest exists; missing legacy metadata does not imply zero omissions. The complete manifest remains bound in work-plan evidence. Deterministic selection, planning/execution separation, model invocation, campaign state, and authority are unchanged.

The PR also corrects the required Quality Gate's source binding: pull-request audits now check out and verify the exact PR head rather than GitHub's synthetic merge ref. The workflow contract test asserts that exact-head source identity is used consistently. Initial hosted checks exposed a stale test assertion for the former `$GITHUB_SHA` contract; it was updated to enforce the new exact-head contract, and the corrected candidate passed.

## Verification and merge

The exact candidate was `582ed1f0d5398822946bfad271250387c9677bfd` (tree `99167a5be065e00a421a2f410996c83905146b3c`), based on main `7ba5c69b71b74ae358fd754942ae320810c75e64`. Independent GitHub compare/readback verified six changed blobs and no other paths. Fifty-eight focused planning, allocation, projection, history, execution-separation, and workflow-contract tests passed on the feature candidate; after fixing the stale contract assertion, all five privileged-audit contract tests passed locally. Compilation and YAML parsing passed, and the full Mypy ratchet showed zero new errors (1,050 matched, 40 retired).

On the exact PR head, hosted source validation, CI, Codex CI, Docker, invariants, lint, gradient regression, release validation, and Helm checks passed. The exact-head hosted Quality Gate run `39373974290` passed with actual Administrator effective UID 0, strict audit and immutability checks, and source SHA/tree bound to `582ed1f0d5398822946bfad271250387c9677bfd` / `99167a5be065e00a421a2f410996c83905146b3c`. Its separate pre-publication metadata guard returned `pr_metadata_guard_ready`; hosted finalizer and acceptance evidence were uploaded (artifacts `12243005532` and `12242945679`, with Quality Gate evidence `12243090016`). Hosted source validation run `39373951193` passed the integrated resource-to-cognition lifecycle and canonical planning/execution separation.

PR #2469 was merged using the regular merge method as `ce9ebd9afa81ee9d0ed365b1ee376437b4c539f3`, tree `99167a5be065e00a421a2f410996c83905146b3c`, ordered parents `7ba5c69b71b74ae358fd754942ae320810c75e64` and `582ed1f0d5398822946bfad271250387c9677bfd`. GitHub reports a valid merge signature; main points to this exact commit. Post-merge Quality Gate, CI, Codex CI, invariants, docs deployment, Docker, Helm, CPU smoke, and source validation all passed on the merge SHA. Forge smoke was skipped by workflow condition.

## Operational observation

At 2026-10-20T05:25:28Z, no scheduled workflow run was bound to current main `ce9ebd9afa81ee9d0ed365b1ee376437b4c539f3`. The latest Federation Health scheduled run remained #39347148781 on older SHA `b69d75884bcf3e33c6a877d0bcdd454311a87f53`; health report generation passed under Administrator authority, but publication failed because repository settings disallow Actions-token PR creation. No current-main scheduled Federation Health or nightly result is claimed.

No production inference, campaign, or transition execution was performed. Protected and stale workspaces remain untouched.

## Next dependency

Use bounded prior-projection omission feedback in the next canonical planning decision while preserving evidence identity and non-execution guarantees. Continue investigating a legitimate, narrowly scoped publication authority for scheduled Federation Health without weakening its Administrator checks or granting broad write permission.
