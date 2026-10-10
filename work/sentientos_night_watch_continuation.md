# SentientOS long construction continuation

Non-authorizing progress record. Construction changes are **untested and unverified for production**. Branch: `codex/construct-sentientos`.

## Latest remotely verified checkpoint

GitHub Git-data commit `f07993732af4935f167fe8a8e86b47a8bea2c56c` contains the cross-platform recovery increment and was fetched by commit SHA. Its continuation-note blob and `sentientos/installation_state.py` were reread through the branch. The commit's parent is `781cdc3b43e0f5fabb81a4a0b9eba11dde2a503b`. Local Git `HEAD` is historical and is not the remote branch identity. Continue with GitHub Git-data commits plus compare-and-swap ref publication.

## Current constructed connections

- Windows has an import-safe `flock` facade, reparse-safe bounded custody readers, and an installation-scoped read-only view. The view derives the fixed machine root from installation identity, validates it by held Windows handles and exposes no write or lock methods. POSIX mutation behavior remains unchanged.
- Windows daemon recovery can read the exact configured resident model-transition protocol and journal. A separate transition-custody inspector verifies request packets, bounded receipt chains and journal references without consuming a packet, appending a receipt, retrying a stage, or invoking inference. Process transition remains POSIX-only.
- Successor software and model-replacement readers preserve canonical identities, bounded evidence and incomplete/interrupted posture. Reconstructing an interrupted model replacement does not replay its inference endpoint.
- World-State has an explicit proposal-review projection; a new fulfillment-receipt bridge now additionally binds the full v2 receipt, preserves proposal/review/handoff references, rejects duplicate identity conflicts, and emits only a digest-bound fulfillment claim. It marks receipt creation time separately from effect time and asserts no authority or actual effect.
- The projection config accepts the existing v1/v2 selections and a v3 explicit fulfillment selection. The daemon re-reads selected receipts on each board build, reports degraded/missing/omitted selections, and makes verified historical claims available to existing configured epistemic and later-tick self-model paths as interpretation, with unknown freshness.
- Earlier local construction continues to harden epistemic state, developmental history, resource evidence, admission, and invocation recovery. Writes stay fail-closed where equivalent atomic Windows publication and custody are unavailable.

## Verification and limits

Changed Python files compile and `git diff --check` passes. No pytest, mypy, runtime execution, Windows execution, provider/model activation, real-world observation, or production verification was performed. Cross-platform installation-backed mutation, activation, serving, transition execution and atomic publication remain unsupported. The fulfillment receipt is a fulfiller claim only; it does not demonstrate that an external action occurred. Current embodied independent-observation input still lacks an authenticated observer issuer.

## Next executable task

Continue the configured causal path after fulfillment by identifying the first existing owner that can verify a real independent consequence or governed execution receipt. Preserve receipt-versus-effect distinction, exact proposal/review/fulfillment lineage and event time. If the source only contains caller assertions, keep them historical/unknown and advance another source-backed causal handoff, especially whether resource evidence can inform a later proposal without creating a resource-minimization motive.
