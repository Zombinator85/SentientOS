# Sequence 642: Recover provisioned Windows replay histories through retained private handles

Windows can now inspect and cryptographically verify an already provisioned private peer replay history while retaining every input handle through the complete bounded read. Missing roots still fail closed and are not created. At this sequence Windows publication and runtime source composition remain disabled.

Candidate `73dfe7e66a3e6baa5c62434e1beea1c42eb436b7` was merged by PR #2747 as `3c415a11fa924105c94a949725cf3dfad84e8f36` with tree `95d1db2168420f1d8d517dc130271d1932e15adc`. All applicable exact-candidate and post-merge checks passed; native Windows acceptance passed 8 exact nodes. The repository checkpoint at this point is recorded in the following construction source increment.

Evidence: `work/construction/evidence/0642-recover-windows-peer-replay-history.json` (SHA-256 `c788d5723ca083e44426b2851465f4508e718c811b59fb943be8482493387f33`).

Artifact manifests and decoded workflow logs were read. Independent ZIP-byte verification was unavailable under the session network policy and is not claimed.
