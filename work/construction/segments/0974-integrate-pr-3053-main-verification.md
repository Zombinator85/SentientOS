# Sequence 974: integrate PR #3053 and verify post-merge main

Sequence 973 was published through PR #3053 as candidate c3da5e62d9dcdddbd59d223ebc10c791d9ed175b. Its exact-candidate Required Quality Gate, full CI, source validation, strict documentation check, Docker, Codex, Invariant, Gradient, Release, and Lint checks passed; the conditional First PR Welcome check was skipped. PR #3053 merged normally as df06079987d951f80fc3bc4a6632c598e0851b80 with tree fd2d434fe43a9a32f2b54d8eeea8d474a53548a7.

All observed post-merge workflows passed: CI, Required Quality Gate, Codex CI, Docker Image, Docs Deploy, and Invariant Tests. Forge Smoke was skipped by condition. Full construction custody verified all 973 predecessor sequences before this append, and fresh GitHub and Git CLI readbacks agreed on main and its tree.

The strict Sphinx linkcheck passed on the PR in about 215 seconds with four HTTP 429 backoffs, and on main in about 94 seconds with two. CI has one linkcheck invocation per full run; Docs Deploy is a separate HTML deployment. Earlier one-worker testing was slower, and a cache would stop checking live links. The evidence does not support a change that improves latency while preserving strict, fresh verification, so the required command and frequency remain unchanged.
