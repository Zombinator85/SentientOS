# Sequence 1006: integrate PR #3087 post-merge verification

PR #3087 merged through the standard GitHub route as `3ec45392ec7554807bf877f33a40055c1bcb421a`; the tree matches the exact candidate `1b0ea1724778af958bb7f8072548418551df3a52`. Remote `refs/heads/main` was read back at that commit and tree. All eight exact candidate workflows passed, including the hosted Required Quality Gate and full CI.

All post-merge workflows passed: Required Quality Gate, CI, Codex CI, Docker Image, Invariant Tests, and Docs Deploy. Forge Smoke was conditionally skipped. CI completed its Helm/Kubernetes test, full self-check, source validation, documentation build, and strict Sphinx linkcheck. The v3 chain retains all 1,005 predecessor records; run, artifact, job, and checkpoint identities are recorded in the evidence sidecar.
