# Phase 92 Provider Credential Custody Manifest — No Secrets Exec Plan

## Goal

Add a deterministic provider credential custody manifest and custody preflight artifact that defines the evidence a future real provider transport would need for credential custody without accepting, storing, reading, resolving, validating, or using real credentials.

## Non-goals

- No secret values, secret references, environment variable reads, secret-file reads, vault/keychain/cloud-secret access, OS credential access, endpoint URLs, auth headers, provider clients, sessions, sockets, HTTP clients, request/response handles, provider SDKs, provider invocations, model calls, semantic generation, tool calls, memory access, retention, routing, admission, execution, or orchestration.
- No change to `prompt_assembler.py` or live `assemble_prompt(...)` behavior.
- No mutation of the Phase 90 registry, Phase 91 capability manifests, or Phase 91 registration preflights.

## Phase 61 through Phase 91 dependency chain

Phase 92 extends the context-hygiene spine after ContextPacket schemas and receipts (Phase 61), truth-gated and blocked-risk selection (Phases 62 and 62B), embodiment/privacy adapters (Phase 63), prompt preflight through adapter/audit/policy/operator-review contracts (Phases 64-78), synthetic and internal no-LLM candidate/display/model-call review contracts (Phases 79-83), non-sendable provider dry-run/review/simulation/network-egress/null-transport contracts (Phases 84-89), the null-only provider transport registry (Phase 90), and the real-transport-forbidden capability/registration preflight contract (Phase 91).

## Credential custody manifest is not credential custody

The manifest is a custody declaration and denial/preflight contract only. It produces posture metadata, forbidden-evidence findings, custody gaps, optional Phase 91 linkage, proof markers, and deterministic digests. It never produces credential values or credential-use authority.

## No-secret invariant

The default manifest is `credential_custody_no_secrets`. All secret material, secret references, secret resolution, environment access, file access, vault access, keychain access, cloud-secret access, endpoint material, provider-client material, network access, provider send, provider SDK use, semantic generation, memory, retention, tools/actions, routing, admission, execution, and runtime authority remain forbidden.

## Future vault contract placeholder

`credential_custody_future_vault_contract_placeholder` is metadata-only. It is allowed only as a future evidence gap marker and must not include a vault path, keychain item, cloud-secret resource ID, environment variable name, secret file path, endpoint URL, credential reference, or any resolver authority.

## Real secret, secret-reference, endpoint, and client access remain forbidden

Forbidden custody kinds cover inline, environment, file, keychain, vault, cloud-secret, provider-client, and unknown custody. The preflight denies requested secret resolution, env/file/vault/keychain/cloud-secret access, endpoint material, provider-client material, network access, and real credentialed registration.

## Preflight behavior

The preflight defaults to denial and returns `credential_preflight_no_secrets_allowed` only when the manifest is clean no-secret metadata, the requested custody kind is one of the three Phase 92 metadata-only kinds, all requested access flags remain false, all no-secret/no-runtime/no-network flags remain true, linked Phase 91 capability metadata is null-only if present, and linked Phase 91 registration preflight remains a null-compatible metadata preflight if present.

## Secret detection behavior

Conservative metadata scanning denies likely secret or secret-locator patterns, including `sk-`, API-key wording, bearer/authorization markers, token/password/secret/client-secret/private-key markers, environment markers, secret file path markers, vault/keychain/cloud-secret markers, and endpoint URL markers. Explicitly negative marker names such as `secret_resolution_forbidden` and `provider_send_forbidden` are treated as metadata-only declarations, not secret access.

## Digest behavior

Custody digests and custody preflight digests are deterministic over stable metadata fields and exclude nondeterministic timestamps. They change when custody kind, declared/forbidden properties, custody flags, linked capability/registration digests, requested custody kind, requested access flags, findings/warnings/constraints/gaps, or no-secret/no-runtime/no-network markers change. They must not include real secrets, prompt text, raw payloads, credentials, endpoints, provider handles, network handles, runtime handles, or provider/model parameters.

## Guardrail behavior

The Phase 75 prompt-boundary guardrail scans the new module by default. It fails forbidden imports or calls for prompt assembly, memory, action, retention, routing, orchestration, provider SDKs, network clients, sockets, HTTP, secret access, vault/keychain/cloud-secret SDKs, and runtime side-effect surfaces. Metadata-only negative marker names remain allowed.

## Tests

`tests/test_phase92_provider_credential_custody_manifest.py` covers default no-secret manifest/preflight behavior, forbidden custody kinds, secret-looking metadata denial, requested access flag denial, Phase 91 linkage, mutation resistance, helper predicates, deterministic digest changes, static no-call/no-import checks, null-only registry preservation, Phase 63 metadata chaining, blocked attempted candidates, adversarial markers, and Phase 75 guardrail coverage.

## Deferred work

Future phases may add a separate operator-reviewed credential custody review or real transport capability review. Such work must still keep real secrets outside context-hygiene metadata, require explicit authority boundaries, preserve the null-only default registry until changed by a later governed phase, and add new guardrails before any real provider transport, credential resolver, endpoint/client construction, or network egress path exists.
