# Sequence 337: record verified transition lineage integration

## Increment and source identity

Sequence 336 added a production-only preflight for the resident A→B→A transition ingress. Before non-synthetic composition, the daemon now loads the exact predecessor-A and successor-B model-replacement protocols and provenance manifests from its configured artifact store, verifies active model identity matches and frozen causal-context custody, and requires each context to declare a bounded repository-generation identity. The declaration is carried into read-only operator status and the model-succession projection as frozen context, not a measurement of the running daemon's source. Synthetic rehearsal remains separate; this does not activate models, grant inference or history authority, or establish a production transition.

The exact candidate head was `91e2427c620a14767034612f53cc9ea0c75af8d5`, tree `7621184456b05876b07dfd215669abef031c91e1`, based on sequence 335 merge `1be514e5d98dc33e643caaa622bc3e7328bf5837`. Draft PR #2326 was merged using the regular merge method. Main is now `26a71f64f89b57d9fd40ef870e69b02baee17bb6`, with tree `7621184456b05876b07dfd215669abef031c91e1` and parents `1be514e5d98dc33e643caaa622bc3e7328bf5837` and `91e2427c620a14767034612f53cc9ea0c75af8d5`.

## Verification

The hosted Required Quality Gate executed 29 selected nodes with 29 passes, zero failures, and zero skips. The new positive transition-lineage test is present in the provenance. Strict Administrator audit and immutability audit passed with no issues; strict audit status was `healthy_strict`. The hosted privileged finalizer reported `ready_for_pr_metadata` with no reasons. Full candidate CI, including the FastAPI TestClient regression, resource-to-cognition lifecycle, documentation link-check, and Helm integration, passed. The local canonical runner remains blocked before collection by this sandbox's package-proxy restriction; local compilation, whitespace checks, and 336-segment continuation custody passed.

Three earlier hosted attempts are preserved rather than rewritten: the first exposed a test-fixture root error, and two later finalizer attempts saw stale PR-title metadata. The fresh reopened event passed. Their exact run and artifact identities are in the append-only evidence record.

Post-merge CI, Required Quality Gate, Docker, invariant tests, Codex CI, and Docs Deploy all passed on the exact main commit. The post-merge quality gate again executed 29 nodes with zero failures or skips, and strict Administrator and immutability audits passed. Forge Smoke was skipped by configured workflow conditions. The separate post-merge feedback invitation failed with HTTP 403 because its integration lacks issue-comment permission; this optional notification is not a source-validation check.

The changed-output Federation Health publication fixture remains undispatched; its successful production publisher run was a no-op because its report matched main. The prior scheduled run and its artifact are recorded in sequence 335. A production A→B→A campaign still requires commissioned model identities, a prepared installation, and an operator-approved protocol.

## Next dependency

The transition now binds exact model and frozen software declarations, while the resident protocol independently binds its initial durable history boundary. The next useful causal bridge is to verify that the exact bounded history selected by each frozen model-replacement context is present with matching record digests in that initial resident boundary before transition ingress. This should fail closed on absent or substituted selected history and preserve the distinction between a controlled comparison context and the running process's complete history.
