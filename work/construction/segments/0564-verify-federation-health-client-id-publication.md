# Sequence 564 — verify Federation Health publication with the configured Client ID

The repository owner added `SENTIENTOS_FEDERATION_HEALTH_APP_CLIENT_ID` to repository secrets alongside the existing App ID and private key. PR #2587 restored the supported, non-deprecated `client-id` action input and updated the hosted workflow contract test. The resulting token remains scoped to SentientOS with only contents and pull request write permissions.

A refreshed intermediate candidate was correctly rejected by the strict finalizer because its merge commit subject did not match the PR title. Recovery retained both histories: the final candidate has verified main as first parent, the earlier candidate as second parent, and an exact title match. Its source delta is reconstructible from the main parent. The final candidate passed the 47-node hosted Quality Gate, privileged finalizer, separate pre-publication metadata guard, CI, Invariants, Docker, Release, Lint Benchmark, Gradient, and Codex CI.

PR #2587 merged normally as `18fb9c7030945c2a5341d510d283e0ced47b709f`. Federation Health push run 39679872709 then passed hosted Administrator preflight and report generation. App token creation succeeded with the configured Client ID, and the publisher opened PR #2588 automatically as the App bot without manual workflow approval. The receipt binds run 39679872709 to main `18fb9c7030945c2a5341d510d283e0ced47b709f` and report digest `e6a98f8e9d89cc626eb6a329fb9c0c26d289f8de6200db37a577044ca793959c`.

PR #2588 changed only the run receipt. It passed strict hosted finalization and the separate metadata guard plus CI, Invariants, Docker, Release, Lint Benchmark, Gradient, and Codex CI, then merged normally as `66b7a6e7852e4044dc754fc31bb489b94be434f8`. The final main push passed CI, Required Quality Gate, Invariants, Docker, Docs Deploy, and Codex CI; Forge Smoke was conditionally skipped.

This verifies unattended execution and publication mechanics. The report still describes a stale configured local log snapshot, not live federation telemetry. No production model transition or inference was run.

Verified main: `66b7a6e7852e4044dc754fc31bb489b94be434f8`, tree `8ee175e584bad31fc9dfbbf19ceadd71cbf124b4`
Latest construction segment: `work/construction/segments/0564-verify-federation-health-client-id-publication.md`
Sequence: 564 (verified operational integration)

Next: continue connecting verified goal execution outcomes to later epistemic planning inputs, preserving read-only planning, exact provenance, and distinct positive and adverse history.
