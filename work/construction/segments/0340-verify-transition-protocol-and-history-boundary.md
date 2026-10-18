# Sequence 340: verify shared transition protocol and complete history boundary

## Source increment and integration

The daemon now requires predecessor A and successor B lineage references to name the same preregistered model-replacement protocol and digest. Read-only projections surface split references as contradictory. Before transition ingress or a verified lineage projection, the resident boundary's record list, ID/digest summary, record-set digest, and canonical boundary digest must agree; selected context entries must resolve to exact resident records. This does not grant history access or transition authority and does not observe running source.

Candidate `b11b5eb76884d40fb1f8ac796e48e1876c11ac19` (tree `f6f9d59be414e149577e937694e777af60f3be6d`) merged normally via PR #2330 as `ebbaa6fa447f30f9ef6bd9254c853d64149bec88`, preserving parents `7d19f2651e8b09bd614322a1ba4ad8b2ae014218` and `b11b5eb76884d40fb1f8ac796e48e1876c11ac19`. Main tree is `f6f9d59be414e149577e937694e777af60f3be6d`.

## Verification

Local canonical tests passed 67/67 across transition composition, transition experiment, transition operator, and developmental model replacement suites; compileall and `git diff --check` passed. The candidate QG (`39083363484`) executed the exact privileged acceptance set successfully, with strict Administrator and immutability verification; the hosted finalizer reported `ready_for_pr_metadata`. Candidate CI, lint/Mypy, Docker, invariants, Release, Gradient, and Codex CI passed. After merge, CI `39083651253`, QG `39083651195`, Docker `39083651216`, invariants `39083651247`, Codex CI `39083651213`, and Docs Deploy `39083651205` all passed on exact main. Post-merge QG ran 29/29 exact nodes with zero failures/skips, Administrator UID 0, healthy strict audit, and clean immutability audit. Forge Smoke `39083651242` was skipped by workflow conditions.

A scheduled Federation Health run `39083395122` completed successfully on main `7d19f2651e8b09bd614322a1ba4ad8b2ae014218`, which was the current main at that execution. The Administrator preflight and health update steps passed. The uploaded report exactly matched `docs/FEDERATION_HEALTH.md` (`# Federation Health`, one node, zero recent events, quiet), verified against artifact digest `19aea605b25d2693aa5c6a64ad2a4f32e5bf957a6e79c54535158ca4eddb2872`. The publication job succeeded, while changed-output verification and fixture publication were skipped because output was unchanged. This is real scheduled execution evidence, not changed-output publication evidence.

## Next dependency and evidence boundary

Sequence 341 adds a deterministic count and digest for the exact omitted complement of selected history, after validating the boundary schema and receipt manifest. PR #2331 is open as a draft and its hosted checks are pending. No production A→B→A run or model improvement is claimed. The next scheduled Nightly Audit and Nightly Self Check executions against `ebbaa6fa447f30f9ef6bd9254c853d64149bec88` are not yet available; keep their privilege and least-write boundaries intact. The stale sequence-178 workspace and sequence-286 provenance-loss evidence remain preserved.
