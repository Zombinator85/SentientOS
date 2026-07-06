# Codex Workcell Storage Operator Consent Request Presentation Verifier

`codex_workcell_storage_operator_consent_request_presentation_verifier.v1` is the deterministic metadata-only verifier for `codex_workcell_storage_operator_consent_request_presentation_contract.v1`.

The verifier reads a required presentation boundary contract JSON and optional supporting consent-ladder JSON reports, records raw-byte `sha256` digests and byte sizes, and emits deterministic JSON plus optional deterministic Markdown. It verifies only structure. A verified presentation-boundary structure is still not presentation.

## CLI

Use the canonical flag first:

```bash
python scripts/verify_codex_workcell_storage_operator_consent_request_presentation_contract.py \
  --storage-operator-consent-request-presentation-contract-json /path/to/presentation_contract.json \
  --output /tmp/presentation_verifier.json \
  --markdown-output /tmp/presentation_verifier.md \
  --summary
```

`--presentation-contract-json` remains a legacy alias. If both flags are supplied, they must be the same path string or the CLI exits `2` with a clean input error. Missing files, invalid JSON, or non-object JSON are rejected with exit code `2` before any report is written.

## Exact output sections

The JSON report includes top-level non-authority flags, `input_summaries`, `presentation_contract_summary`, `optional_context_summary`, `verification_status`, `verification_checks`, `presentation_surface_results`, `presentation_authority_requirement_results`, `operator_attention_requirement_results`, `delivery_scope_requirement_results`, `request_packet_integrity_requirement_results`, `response_path_requirement_results`, `denied_inference_results`, `missing_real_world_presentation_results`, `reviewer_hygiene_summary`, `violation_summary`, `sentientos_mount_alignment`, `future_activation_requirements`, and `non_authority_posture`.

`presentation_contract_summary` records the presentation contract ID when present, the observed metadata/future/non-authority flags, derivable inventory counts, non-authority posture presence/all-true status, and source digest algorithm, digest, and byte size. `optional_context_summary` is deterministic for every optional input and marks omitted inputs as not provided; supplied context rows are `context_only` and include detected IDs/statuses when derivable.

## Verification status meanings

Allowed statuses are exactly:

- `storage_operator_consent_request_presentation_contract_verified`: every violation-severity structural check passes.
- `storage_operator_consent_request_presentation_contract_failed`: major sections are evaluable, but required flags, IDs, or values are wrong.
- `storage_operator_consent_request_presentation_contract_incomplete`: major inventories/requirements/denied-inference/gap sections are missing or not lists, so the verifier cannot evaluate the boundary as proper sections.

`verification_status` is structure-only. It does not imply consent, runtime authority, storage activation, readiness, daemon authority, federation authority, ledger authority, glow authority, finalizer authority, PR metadata authority, or presentation authority.

## Non-authority posture

The verifier does not present a request, render UI, send messages, deliver externally, create a response artifact, collect response, collect consent, imply consent, bind runtime authority, activate memory or storage, write ledger entries, archive glow evidence, mutate memory, watch files, poll state, run commands from inside the verifier, call providers, call networks, schedule tasks, create tasks, send alerts, trigger daemon action, decide readiness, authorize commits, authorize PR metadata, create PRs, establish federation consensus, or train/modify models.

Operator silence, notification delivery, message delivery, local files, or displayed copies cannot imply consent. Request packet existence, evidence dossier completeness, response contract existence, response verifier success, finalizer readiness, PR metadata guard readiness, matrix readiness, daemon state, federation state, storage policy, runtime authority contracts, or consent-design evidence cannot imply presentation authority.

Reviewer URL hygiene remains metadata-only and separate from runtime behavior. It helps reviewers ensure no bad ``OpenAI` organization repository attribution for SentientOS` repository attribution reappears while preserving legitimate OpenAI API/model/ChatGPT/Codex references.

## Mount alignment

The verifier reports relation to `/ledger`, `/glow`, `/vow`, `/pulse`, and `/daemon` only as metadata: no ledger write, no glow archive, no vow mutation, no pulse activation, and no daemon action occurs.

## Markdown report

The deterministic Markdown report includes sections for input summaries, presentation contract summary, optional context summary, verification status, verification checks, all result sections, reviewer hygiene summary, violation summary, SentientOS mount alignment, future activation requirements, and non-authority posture. Table cells escape pipes and newlines.
