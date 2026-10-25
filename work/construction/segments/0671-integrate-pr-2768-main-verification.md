# Sequence 671: integrate the sequence 670 publication on main

PR #2768 candidate `1b4ed3c8fcc45e0ae58ab9ff2295aeb7092be524` merged normally as `704ae9dbfa1cb58054cbf5bc9ca43e3a3ca9ad84`. The merge commit has parent main `00b8cc00e5d1b30e892fe380ec95bb6978f17712` and the exact candidate tree `39d6402845f926c579f32ef73546d530d3f00d58`. A read-only `git ls-remote` and fetch verified that remote `main` points to the merge commit.

The exact-head hosted Required Quality Gate passed as run `40206761878`, including hosted Administrator audits, pre-commit reconstruction, privileged landing finalization, and the pre-publication metadata guard. Exact-head CI run `40206616169` passed. Release `40206616157`, Gradient null regression `40206616219`, Invariant Tests `40206616174`, Codex CI `40206616222`, Docker Image `40206616246`, and Lint Benchmark `40206616180` also passed.

Post-merge Required Quality Gate `40207015493`, CI `40207015502`, Docs Deploy `40207015481`, Invariant Tests `40207015490`, Codex CI `40207015528`, and Docker Image `40207015547` all passed on merge commit `704ae9dbfa1cb58054cbf5bc9ca43e3a3ca9ad84`. Forge Smoke was skipped by its workflow conditions.

The first exact-head Quality Gate runs exposed a metadata binding issue: the PR title still matched the earlier commit rather than the new commit subject, which the hosted landing guard requires to match exactly. Updating the title to the published commit subject allowed reconstruction and finalization to pass; no candidate source change was made for this correction.

The approval review was triggered by uploading the full append-only construction index blob to GitHub and cited the index's project history/metadata and the GitHub destination. The user explicitly approved the exact sequence 670 index and evidence upload. All seven changed blobs were read back byte-for-byte, the uploaded tree matched the local candidate tree, and the exact-head branch update and normal PR merge completed. The connected execution and GitHub tools expose no standing approval, trusted-destination, or allowlist control. No alternate transport was used. Bundling several append-only increments into one normal PR update can reduce the number of index uploads, but it does not remove the platform review; a persistent exception requires a platform-supported trust/approval setting that is not available here.

Latest verified main: `704ae9dbfa1cb58054cbf5bc9ca43e3a3ca9ad84`, tree `39d6402845f926c579f32ef73546d530d3f00d58`.
