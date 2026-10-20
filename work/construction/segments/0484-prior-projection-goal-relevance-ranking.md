# Sequence 484 — prioritize goal-relevant prior projection

## Source increment

PR #2471 makes the bounded verified prior-projection owner prioritize epistemic propositions tagged by enabled canonical goals, using the same deterministic goal precedence as planning. The projection and omission manifest versions bind the selection policy and priority identities. Omitted identities, source tick cutoff, and positive or adverse historical posture remain verifiable. Canonical planning consumes the same loaded goal graph and does not execute goals or invoke inference.

The increment addresses a concrete integration defect: four historical records were protocol-bound while the relevance selection could retain only three, and lexicographic truncation could omit the goal-relevant record. The fix ranks goal-relevant propositions first within the existing state bound and preserves the complete omission evidence.

## Verification and merge

The exact candidate `a59a211ab2d852ef69c1f1fe87988b6f456766fe` (tree `61078b4c3347b7940136cfffe008f3f9640780cb`) was based on main `c684e425d9ddb80f91215eef7c244c55a4be4681`. PR #2471 changed four source and test files; independent candidate-tree readback confirmed all four blobs. Local affected staging, planning, progression, and history-comparison verification passed 147 tests. Exact-node acceptance passed, targeted Mypy passed, full Mypy remained at 2,698 diagnostics with zero added or retired, and compilation passed.

The exact-candidate hosted Quality Gate run `39376929695` passed with actual Administrator UID 0, strict audits, source-bound acceptance, immutable audit evidence, and the separate pre-publication metadata guard (`pr_metadata_guard_ready`). All PR checks passed. PR #2471 was merged with the regular merge method as `800dcef026b32c45c5668282b260ca2e39ab4c24`, tree `61078b4c3347b7940136cfffe008f3f9640780cb`, ordered parents `c684e425d9ddb80f91215eef7c244c55a4be4681` and `a59a211ab2d852ef69c1f1fe87988b6f456766fe`. The merge commit is GitHub signature-verified.

Post-merge Quality Gate run 39377357918, CI/build run 39377358087, source validation and full self-check run 39377357958, Docker/CPU smoke run 39377357897, invariants run 39377358041, deployment run 39377357939, Helm, and documentation link checks all passed on the merge SHA. Forge smoke run 39377357921 was skipped by workflow condition.

## Operational observation

At 2026-10-20T05:58:51Z, GitHub Actions showed no scheduled Federation Health, Nightly Audit Integrity, or Nightly Self Check run on the current main head. The latest Federation Health scheduled run remained #39347148781 on older SHA `b69d75884bcf3e33c6a877d0bcdd454311a87f53`: its Administrator health/report job passed, while PR publication failed because repository Actions-token policy disallows Actions-created pull requests. No current-main scheduled execution is claimed.

No production inference, campaign, or transition execution was performed. Protected and stale workspaces remain untouched.

## Next dependency

Continue making retained historical experience influence canonical decisions through bounded, deterministic, provenance-bound inputs. Preserve planning/execution separation, positive and adverse outcomes, explicit omission evidence, and authority boundaries. Investigate the missing current-main scheduled evidence and the repository-level Actions PR-creation policy without bypassing governance.
