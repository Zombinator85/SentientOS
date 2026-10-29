# Sequence 1011: integrate PR #3092 post-merge verification and investigate duplicate linkcheck latency

PR #3092 merged through the normal squash route as `efb54d647c3afe6031bdcc95d18f57bc87aea609`; the exact candidate tree was preserved. Remote main readback matched. All eight exact-candidate workflows passed, including Required Quality Gate and CI.

All post-merge workflows passed or were conditionally skipped: Required Quality Gate, CI, Codex CI, Docker Image, Docs Deploy, Invariant Tests succeeded; Forge Smoke was skipped by condition. CI completed source validation, self-check, Helm/Kubernetes, docs build, and strict Sphinx linkcheck.

The exact PR merge tree and post-merge main tree are both `924c4f5bc37ec48f2ae3963a59e607f4a7a53efd`. Both CI events ran the strict linkcheck against 619 documentation source files. PR docs job 123750931796 took 4m34s; its linkcheck ran 21:44:39–21:48:51 UTC and logged five GitHub rate-limit waits before succeeding. Post-merge docs job 123753598030 took 2m36s; its linkcheck ran 21:50:22–21:52:34 UTC and logged three rate-limit waits before succeeding. No check failed and no verification was bypassed.

Because the merged tree is identical, the main push repeats the strict external linkcheck already completed for the exact PR merge tree. Investigate a narrowly scoped workflow condition that keeps the strict linkcheck mandatory on pull requests while retaining the documentation build and all other CI checks on main pushes. Validate the condition in hosted CI before integration; do not change retry policy or link validation rules.
