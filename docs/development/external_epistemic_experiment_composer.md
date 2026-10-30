# External epistemic experiment composer

The composer connects the existing persistent epistemic projections and
revision-case answer keys to the existing external inference custody path. It
does not create grants, admissions, service configuration, or truth judgments.
The runtime caller still supplies the configured service, exact invocation,
operator-owned admission, credential handle, and controller.

`prepare_external_request` binds one preregistered before/after prompt, case
commitment, proposition projection, semantic packet, exact model ID, and
generation parameters into transient request bytes. The default encoder is
provider-neutral. `OpenAIResponsesRequestEncoder` is the explicit model-aware
encoder for JSON-only Responses API requests; its matching decoder accepts one
assistant output-text segment and rejects tool output, incomplete responses,
and ambiguous response shapes. The requested model ID and any provider-reported
model ID are recorded separately. Provider-managed weights remain unknown.

`OneShotEpistemicRequestMaterialSource` stores only in-memory mutable bytes and
requires the complete existing `RequestMaterialBinding`. The existing governed
resolver still validates the catalog, exact request digest, and current runtime
admission, then clears the source and returned buffers. A material is consumed
once; it is not a persistent request store.

Pass `ExternalResponseCapture` as the existing controller's response consumer.
It copies one bounded, transient response before the controller clears its
buffer. `score_external_observation` requires the exact request/service binding
and matching durable hash-linked receipt, verifies response provenance and
digest, and scores the parsed answer against the committed independent key.
Reports retain negative and incomplete outcomes, exact request/configuration
and receipt digests, model labels, and explicit unknown artifact identity. Raw
request and response content and private answer keys are not written to the
receipt store or report. The current receipt schema does not expose the full
result envelope (including HTTP status), so the composer reports its
`result_digest` as opaque; it does not claim to recompute that digest. The
existing controller validates the full result before persisting the receipt.

`compare_external_pair` checks proposition identity, state preservation or the
allowed correction transition, evidence-set changes where required, generation
controls, and exact provider-reported model labels. A provider-managed model
replacement cannot qualify because artifact identity is unavailable. Synthetic
fixtures may exercise scoring and provenance, but they remain `insufficient`
for real-model qualification. An unreported or mismatched model label likewise
prevents pair qualification.

For managed cloud egress, pass
`managed_https_proxy_connection_factory()` into the existing
`ExactHTTPSExternalModelTransport` as its connection factory. It reads only the
HTTPS proxy setting, uses an HTTP proxy's CONNECT tunnel to the configured
endpoint, and leaves verified TLS to the exact endpoint. It rejects proxy
credentials, paths, query strings, fragments, and HTTPS-to-proxy TLS because
the current authority profile has no governed representation for those. It
does not forward provider credentials to the proxy, follow redirects, or retry.
Without a configured proxy it retains the existing direct connection mode.

The `runtime` optional dependency and `requirements-full.txt` already declare
`keyring>=24,<25`; this change preserves those declarations. A missing keyring
credential remains a sanitized unavailable-credential outcome. Compose
`FailClosedOSKeyringCredentialBackend` into the existing
`GovernedCredentialResolver` when the runtime extra may be absent; it converts
only `keyring` import failure into the existing
`credential_backend_unavailable` error. It does not read environment variables,
provision credentials, or add a credential-management surface. No provider
calls are made by construction or tests.

The experiment remains a measurement instrument, not an empirical result. A
real run requires an independently registered case/answer key, exact configured
service and request payload digest, a valid current operator runtime admission,
and a credential provisioned under the exact service and opaque reference in
the OS keyring. Its results must retain all failed and negative observations.

For the checked-in task acceptance manifest, run the repository test wrapper
with `SENTIENTOS_TEST_RUN_DIR=.codex-tmp/test_runs`; this keeps the append-only
test provenance in the ignored runtime area named by the manifest. Hosted
Quality Gate runs provision their own external test-run directory and construct
their acceptance manifest from that exact run.
