# Host live-grant readiness runtime

`sentientos/host_live_grant_readiness_runtime.py` closes the same-tick review loop from an in-memory `HostControlledAuthorizationEvaluation` into deterministic live-grant readiness review evidence. The chain is:

1. exact controlled-authorization runtime evaluation;
2. validated controlled ledger and safety satisfaction manifest;
3. live-grant prerequisite matrix;
4. operator/policy approval **request** packet;
5. grant-issue preflight receipt;
6. denial/deferral receipt;
7. atomic external evidence bundle;
8. terminal World-State review facts;
9. authenticated read-only dashboard projection.

The runtime uses only `AuthorityClass.PROPOSAL_EVALUATION` metadata admission. It does not request privileged-effect admission and does not treat admission as operator approval, policy approval, local authorization, fulfillment, or execution permission.

## Truth boundaries

The runtime is readiness-only and approval-packet-only:

- no operator approval is fabricated;
- no policy approval is fabricated;
- no `LocalAuthorizationGrant` is issued or activated;
- no fulfillment is authorized;
- no backend executes;
- no host mutation occurs;
- no effect, rollback, or postcondition proof is inferred from metadata labels.

Controlled ledger presence is schema/ledger evidence, not a live grant ledger. Safety manifest presence is not permission; individual gate status must remain visible. Approval packets are requests for future operator/policy review, not approval evidence. Preflight records do not issue grants. Denial/deferral receipts are not revocations.

## Identity and custody

Semantic identity includes source IDs/digests, domain/scope, prerequisite statuses, blocked actions, warning/risk codes, and no-authority assertions. It excludes runtime custody timestamps, roots, paths, and process details. Persistence writes atomically beneath an injected runtime-state root and writes only compact review artifacts plus a latest pointer.

## Matrix lane

The required matrix lane is `host_live_grant_readiness_runtime_tests`. It runs the runtime, CLI, live-grant readiness, controlled-runtime linkage, local-grant non-invocation, sentientosd, World-State, dashboard, capability, proof, matrix-contract, and custody tests.
