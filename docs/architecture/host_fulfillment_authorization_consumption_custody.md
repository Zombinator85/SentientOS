# Host Fulfillment Authorization Consumption Custody

`host_fulfillment_authorization_consumption_custody` binds one explicit future-fulfillment request to one exact active local authorization grant and records a metadata-only consumption or denial posture. It composes the existing local authorization grant custody records and the existing fulfillment-authorization request, grant-consumption verification, scope assessment, consumption receipt, and denial receipt builders.

The custody chain is:

1. exact `HostLocalAuthorizationIssueReceipt`;
2. exact active `LocalAuthorizationGrant`;
3. exact local grant verification;
4. exact local authorization ledger snapshot, expiry evaluation, and revocation posture;
5. `HostFulfillmentAuthorizationRequestEnvelope` with bounded actor, subsystem, reason, domain, backend label, scope, targets, and requested time;
6. `HostFulfillmentAuthorizationConsumptionPlan`;
7. dedicated `AuthorityClass.FULFILLMENT_AUTHORIZATION_CONSUMPTION` metadata admission;
8. existing fulfillment-authorization request, grant-consumption verification, scope-match assessment, and receipt/denial records;
9. append-only idempotent consumption ledger;
10. World-State and authenticated read-only dashboard projection.

A successful `authorization_consumed_for_future_fulfillment=true` means only that this exact request was checked against this exact grant, found within scope/target/time bounds, admitted for metadata recording, and recorded once in the append-only ledger. It does **not** grant fulfillment, authorize an executor, admit a privileged effect, invoke a backend, satisfy future gates, prove an effect, revoke a grant, decrement a grant, or mutate the host.

The dashboard endpoint is `GET /api/world-state/host-fulfillment-authorization`. It reads only the terminal World-State snapshot and reports bounded counts, domains, backend labels, scopes, targets, missing future gates, blocked actions, and no-effect flags. It cannot create requests, request admission, consume authorization, append ledger entries, invoke executors, grant fulfillment, or mutate host state.

The CLI is `scripts/build_host_fulfillment_authorization_runtime.py`. Planning and inspection are dry-run by default. `consume` requires `--apply` for successful recording and exact issue receipt, grant, verification, ledger, expiry, and revocation inputs. The CLI never invokes an executor, never grants fulfillment, never performs host effects, and never performs Git operations.

Required matrix lane: `host_fulfillment_authorization_consumption_custody_tests`.
