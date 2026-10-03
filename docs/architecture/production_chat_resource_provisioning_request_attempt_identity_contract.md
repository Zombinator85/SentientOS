# Production provisioning publisher-attempt identity contract

This frozen, deterministic, metadata-only contract defines the future evidence schema `sentientos.production_chat_resource_provisioning_request_publisher_attempt_identity:v1`. It defines evidence; it neither emits nor verifies evidence and grants no authority.

## Why a separate invocation identity is required

Installation identity **I** plus provisioning ID **P** identifies publication custody, not one invocation. Even the request digest, storage hash, byte size, and inert intent digest identify content rather than the actor or invocation that attempted publication. A governed `publication_attempt_id` must identify exactly one invocation, must not alias P, and must be established by the future lifecycle-evidence boundary rather than accepted from an unauthenticated caller or reconstructed after failure.

The closed artifact fields are `schema_version`, `publication_attempt_id`, `installation_identity`, `resource_provisioning_id`, `request_digest`, `request_storage_sha256`, `request_storage_bytes`, `intent_digest`, `publisher_capability_id`, `publisher_principal`, `publisher_authority_definition_digest`, `attempt_started_at`, `attempt_identity_contract_digest`, `synthetic_test_evidence`, and `identity_digest`. It embeds neither request bytes nor a request packet and permits no caller-selected path.

## Exact request binding and ordering

Only after the publisher has constructed and validated its exact actuator-compatible request bytes, request digest, storage SHA-256, byte size, and deterministic intent may a future emitter construct identity evidence. It must consume those exact values—no second schema, translation, normalization, or independent reconstruction. Complete, provenance-verifiable identity evidence must exist before the first durable mutation beneath `local-model/resource-provisioning-requests/P/`, including creation of `request.json` or `publication-receipt.json`.

The identity write would itself be a governed mutation; the law is that attempt-evidence mutation precedes publication-custody mutation. A timestamp comparison cannot prove that ordering.

## Canonical bytes and provenance

The future artifact uses finite canonical JSON: UTF-8, sorted keys, compact separators, ASCII escaping, and a lowercase SHA-256 over every field except `identity_digest`. Durable evidence must use the exact canonical bytes. But a digest proves content identity, not who created the content or when in the lifecycle it was created. Correct fields, self-attestation, matching authority strings, or a valid digest over caller-authored JSON are insufficient provenance.

A future verifier must independently authenticate a separately governed lifecycle-evidence producer, its exact authority and effect surface, binding to the registered publisher definition, exact durable bytes, non-caller authorship, non-synthetic production posture, and mechanical pre-effect ordering. No such producer, verifier, provenance mechanism, or registered lifecycle-evidence authority exists today.

## Future fixed custody

Future custody is `local-model/resource-provisioning-request-attempts/<publication_attempt_id>/identity.json` under authenticated installation state. It is fixed, create-only, immutable, non-overwritable, non-repairable, and has no retry, deletion, or cleanup authority. The path attempt ID must equal the artifact ID, and artifact installation identity must equal authenticated installation identity. P is binding metadata, not a destination. This root is distinct from request-publication custody, so identity evidence is neither request nor receipt publication.

## Authority and recovery boundaries

The artifact binds publisher capability `production_chat_resource_provisioning_request_publish`, principal `deterministic_production_chat_resource_provisioning_request_publisher`, and authority-definition digest `349058b7e6959c06bfae1a8acabd01c6c022245c6fd404e63535cac6ed608cf5`. Existing five-effect publisher authority does **not** include lifecycle-evidence writing and is not widened by this contract.

This contract refines only `pre_effect_publisher_attempt_identity_evidence` in the [recovery-review contract](production_chat_resource_provisioning_request_recovery_review_contract.md). It proves neither publication outcome nor terminality, recovery eligibility, reuse, allocation, or execution. Because emission, custody, independently verifiable provenance, verification, and authority remain absent, `publisher_attempt_identity_evidence_missing` remains open.
