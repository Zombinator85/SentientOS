# Sequence 961: integrate PR #3039 and verify post-merge main

Sequence 960 was published through PR #3039, candidate `16072b8d007cd2dafc0e5513bf374ae819516039`, with tree `e55de275bc91824f68980cafac612d76f1d67473`. Its exact-candidate Required Quality Gate, full CI, Invariant, Gradient, Release, Docker, Codex, and Lint checks passed. The separate push-triggered Invariant Tests workflow also passed. PR #3039 merged normally as `05366654bec18f164eba1730a275e9fa3e8cabac` with tree `e55de275bc91824f68980cafac612d76f1d67473`.

All post-merge CI, Codex CI, Docker, Docs Deploy, Invariant Tests, and Required Quality Gate workflows passed; Forge Smoke was skipped by condition. The strict linkcheck passed on both the PR candidate and main, with two and one GitHub rate-limit backoffs respectively.

The PR run inventory confirms the full CI workflow ran once for the pull request and did not run on the feature-branch push. Main-push CI remains enabled and performed the strict post-merge linkcheck.

Remote `main` readback and tree matched the merge commit. GitHub Git-tree readbacks matched the active checkpoint, constant-size v3 head, latest immutable shard, latest segment, roadmap index, storage consent evidence map, and memory contract. Continuation custody verified all 960 predecessor sequences before this append.
