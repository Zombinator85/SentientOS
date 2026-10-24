# Sequence 643: Retain Windows replay read handles through complete bounded inspection

Windows replay inspection now holds all selected input handles for the full bounded read and repeats identity, metadata, root ACL, and file ACL checks before releasing them. Native regressions proved an earlier file could not be overwritten or deleted while a later file was being read, and that changed ACLs are rejected at the terminal boundary. Runtime composition and publication remained disabled at this sequence.

Candidate `d1ede149d939b184d12d246efeb20e997b6eeb4d` was merged by PR #2748 as `02602fc5f1ff0c03de8845f97a0a69ede5fc8157` with tree `991335491bae471f840f3cc73ae9539b0f6bcae7`. All applicable exact-candidate and post-merge checks passed; native Windows acceptance passed 11 exact nodes. The repository checkpoint at this point is recorded in the following construction source increment.

Evidence: `work/construction/evidence/0643-retain-windows-replay-inputs-through-read.json` (SHA-256 `86438dc9914a5ccb5756e0ff83e262f27543c8d195a3a8b364a9d22fd928f3a1`).

Artifact manifests and decoded workflow logs were read. Independent ZIP-byte verification was unavailable under the session network policy and is not claimed.
