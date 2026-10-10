# SentientOS long construction continuation

Non-authorizing progress record. Construction changes are **untested and unverified for production**. Branch: `codex/construct-sentientos`.

## Latest remotely verified checkpoint

GitHub branch inspection most recently verified `3284f43510f9132a1de8f3e7a592527817925163` (tree `546eb11bcb6c93f38d622ff0586b3fc472eb1c80`, parent `f07993732af4935f167fe8a8e86b47a8bea2c56c`). Local Git `HEAD` is historical and is not the remote branch identity. Continue with GitHub Git-data commits plus compare-and-swap ref publication.

## Current constructed connections

- Windows has an import-safe `flock` facade, reparse-safe bounded custody readers, and an installation-scoped read-only view. The view derives the fixed machine root from installation identity, validates it by held Windows handles and exposes no write or lock methods. POSIX mutation behavior remains unchanged.
- Windows daemon recovery can read the exact configured resident model-transition protocol and journal. A separate transition-custody inspector verifies request packets, bounded receipt chains and journal references without consuming a packet, appending a receipt, retrying a stage, or invoking inference. Process transition remains POSIX-only.
- Successor software and model-replacement readers preserve canonical identities, bounded evidence and incomplete/interrupted posture. Reconstructing an interrupted model replacement does not replay its inference endpoint.
- World-State has an explicit proposal-review projection; a new fulfillment-receipt bridge now additionally binds the full v2 receipt, preserves proposal/review/handoff references, rejects duplicate identity conflicts, and emits only a digest-bound fulfillment claim. It marks receipt creation time separately from effect time and asserts no authority or actual effect.
- The projection config accepts the existing v1/v2 selections and a v3 explicit fulfillment selection. The daemon re-reads selected receipts on each board build, reports degraded/missing/omitted selections, and makes verified historical claims available to existing configured epistemic and later-tick self-model paths as interpretation, with unknown freshness.
- Strategy proposal records now distinguish the invocation request's experiment linkage from authenticated resource-allocation linkage carried by the invocation receipt. The resident World-State builder joins selected proposal records to the separate resource-ledger record by invocation, allocation, attempt, consumption-receipt and effect-receipt identity, checks principal binding and ledger completeness, and emits a bounded historical lineage record. Missing or conflicting selected custody is degraded; legacy unlinked invocations remain unlinked. The joined lineage is prioritized for later resident cognition and carried into review/self-model interpretation as lineage, not consequence or objective.
- Earlier local construction continues to harden epistemic state, developmental history, resource evidence, admission, and invocation recovery. Writes stay fail-closed where equivalent atomic Windows publication and custody are unavailable.

## Verification and limits

Changed Python files compile and `git diff --check` passes. No pytest, mypy, runtime execution, Windows execution, provider/model activation, real-world observation, or production verification was performed. Cross-platform installation-backed mutation, activation, serving, transition execution and atomic publication remain unsupported. The fulfillment receipt is a fulfiller claim only; it does not demonstrate that an external action occurred. Current embodied independent-observation input still lacks an authenticated observer issuer. The new resource-proposal join is source-implemented but not runtime exercised, and its proof is bounded to the configured projected ledger tail.

## Next executable task

Next, connect persisted prediction-comparison outcomes to the existing authorized epistemic-update path without treating unverified observer assertions as independent consequence evidence. Inspect existing source selectors and mutation authority; preserve comparisons as historical/unknown until a real authenticated consequence owner exists. Then advance controlled model/history comparison composition where owner interfaces already support it.
