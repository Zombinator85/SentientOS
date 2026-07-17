# Host local authorization grant custody

`host_local_authorization_grant_custody` seals the explicit local authority-record path after host live-grant readiness. It binds one exact readiness evaluation to a sealed review request, independent explicit operator and policy decisions, a dedicated control-plane admission for local authorization grant issuance, a scoped expiring local authorization grant record, append-only ledger evidence, expiry evaluation, revocation custody, World-State evidence, and a read-only dashboard projection.

This subsystem is local authority metadata only. It does not authorize fulfillment, does not satisfy privileged host-effect admission, does not invoke a backend, does not execute service/process/package/driver/file/provider/network/model effects, and does not mutate the host.

## Custody chain

1. `HostLocalAuthorizationReviewRequest` is built from an exact validated `HostLiveGrantReadinessEvaluation` and binds prerequisite matrix, approval-request packet, preflight receipt, denial/deferral receipt, source tick, correlation, scope, targets, bounds, expiry, revocation posture, blocked actions, and no-effect flags.
2. `OperatorLocalAuthorizationDecision` and `PolicyLocalAuthorizationDecision` are separate typed records. Strict validation rejects sample, demo, default, anonymous, wildcard, blank, and placeholder identities.
3. `HostLocalAuthorizationIssuePlan` binds the request, both decisions, intended grant ID, idempotency key, attempt ID, prior ledger digest, safety lineage, and no-fulfillment/no-effect boundaries.
4. Issuance requests `AuthorityClass.LOCAL_AUTHORIZATION_GRANT_ISSUANCE`; proposal evaluation and privileged host-effect authority classes are not substitutes.
5. An allowed admission can write exactly one scoped `LocalAuthorizationGrant`, expiry evaluation, verification, issue receipt, and append-only ledger snapshot under `SENTIENTOS_RUNTIME_STATE_ROOT`.
6. Expiry and revocation reduce or end authority metadata only. Revocation appends evidence and never authorizes fulfillment.

## Daemon and dashboard boundary

`sentientosd` remains non-issuing: it may observe persisted evidence and project pending review state, but it must not fabricate decisions, call sample approval builders, issue grants, revoke grants, expand scope, or treat local authority metadata as fulfillment authority.

The dashboard endpoint `GET /api/world-state/host-local-authorization` is authenticated and read-only. It reports pending review counts, explicit decision counts, issuance posture, active/expired/revoked/conflicted grant counts, scope/expiry summaries, blocked actions, and latest IDs while preserving `fulfillment_granted=false`, `execution_triggered=false`, and `host_mutation_performed=false`.
