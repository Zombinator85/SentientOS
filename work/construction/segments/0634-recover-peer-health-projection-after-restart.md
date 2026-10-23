# Sequence 634 - recover peer Health projection after restart

Sequence 634 adds a read-only recovery path for the latest authenticated peer-reported Health observation. It revalidates the entire bounded immutable replay chain against the exact trust-catalog version and digest pinned when the records were accepted, verifies each signed envelope at its signed issue time, and applies the current freshness window to the newest event before projecting it.

Recovery returns no projection for empty history, rejects tampering and catalog drift, preserves an adverse latest report, and leaves replay bytes unchanged. The resulting observation continues to deny claim-truth establishment, local Health publication, work admission, planning, execution, and decision power. Recovery does not contact peers or create a listener. Catalog changes fail closed until historical catalog custody is implemented.

The first hosted source-validation attempt correctly rejected three parameter-expanded acceptance identities after the candidate omitted their explicit pytest IDs. A follow-up commit restored the stable IDs without changing test expectations. The corrected exact candidate passed all required PR workflows, the privileged Quality Gate, the separate pre-publication metadata guard, and its source-bound acceptance nodes.

PR #2728 candidate `b9638d080a8507a8eb7a25180641aafd16805754` (two commits, including the identity correction) merged normally as `de698afc55b13f66917cabbc574ad07bdb48fbec`, tree `72dbbf7fe887ec0b07215f3997b394b04584a9db`. The tested main `271eacb2953f58384724bca6348f58bca54fcc46` remains the first parent, and the candidate remains the second parent.

Local focused regressions passed (15 tests); strict Mypy and compilation passed for both modified source modules and the related tests. Hosted source validation separately exercised the peer replay owner, bridge, and restart-safe recovery nodes.

Evidence: `work/construction/evidence/0634-recover-peer-health-projection-after-restart.json`.

Next: connect this read-only reconstruction to the daemon's verified peer-projection owner. Keep peer claims separate from local Health and preserve fail-closed behavior across trust-catalog changes; do not connect a live transport or grant admission, planning, or execution authority.
