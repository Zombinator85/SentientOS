# Sequence 650: Integrate verified sequence 650 documentation on main

PR #2757 documents the Windows peer Health replay-root pin introduced by the verified sequence 648 implementation. Candidate `d8e51bfe83753e2900dec868526ba7a7f0b8a533` merged normally as `91c0545f4f21f06d740c89acd2b9b3f0028ea5e0`, with `69587ba50f08c798b7512bfc82d8f189d059a5e0` as first parent and the exact tested candidate as second parent. Main tree `0d9a5fb0def2e51c88673b4f9b8b91dc63ae7372` matches the candidate tree.

On the exact PR head, Required Quality Gate, CI, Invariants, Docker, Codex CI, Lint Benchmark, Release, and Gradient null regression passed. The Required Quality Gate uploaded its exact task-acceptance evidence and hosted landing finalizer artifacts. On main `91c0545f4f21f06d740c89acd2b9b3f0028ea5e0`, Required Quality Gate, all four CI jobs, Invariants, Docker, Codex CI, and Docs Deploy passed; Forge Smoke was skipped by condition. GitHub advertised the main Quality Gate archive SHA-256 as `4a240349e0b7711bf3d884649f7b49b8cc9471a587086d5ace9ad6237879b081`.

The documentation now describes the Windows v2 pin, volume serial and file ID fields, operator-provisioned private-root requirement, and fail-closed handling of missing or mismatched identity. No production source or runtime authority changed.

Evidence: `work/construction/evidence/0650-integrate-sequence-650-main-verification.json` (SHA-256 `25612079e72490152f48872a9167a4a8d3b033126179dc9eafbd4225197e5c14`).
