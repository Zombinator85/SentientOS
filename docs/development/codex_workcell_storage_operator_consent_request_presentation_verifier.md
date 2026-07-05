# Codex Workcell Storage Operator Consent Request Presentation Verifier

`codex_workcell_storage_operator_consent_request_presentation_verifier.v1` is the deterministic metadata-only verifier for `codex_workcell_storage_operator_consent_request_presentation_contract.v1`.

The verifier reads a required presentation boundary contract JSON and optional supporting consent-ladder JSON reports, records raw-byte `sha256` digests and byte sizes, and emits deterministic JSON plus optional deterministic Markdown.

It verifies only structure. `verification_status` is not presentation, UI rendering, message delivery, response artifact creation, response collection, consent, operator approval, runtime binding, storage activation, readiness, ledger authority, glow authority, daemon authority, scheduler authority, model authority, or federation authority.

## CLI

```bash
python scripts/verify_codex_workcell_storage_operator_consent_request_presentation_contract.py \
  --presentation-contract-json /path/to/presentation_contract.json \
  --output /tmp/presentation_verifier.json \
  --markdown-output /tmp/presentation_verifier.md \
  --summary
```

Missing files, invalid JSON, or non-object JSON are rejected with exit code `2` before any report is written.

## Verified boundaries

The report verifies the contract ID and non-authority flags; inactive future-only presentation surfaces; unsatisfied presentation authority, operator attention, delivery scope, request packet integrity, and response path requirements; denied inferences; blocking inactive missing-presentation gaps; future-only unmet activation requirements; reviewer hygiene URL metadata; and `/ledger`, `/glow`, `/vow`, `/pulse`, and `/daemon` mount alignment without activation or writes.

The verifier does not present a request, render UI, send messages, deliver externally, create response artifacts, collect responses, collect or imply consent, bind runtime authority, activate memory or storage, write ledger entries, archive glow evidence, mutate memory, watch, poll, schedule, alert, create tasks, call networks or providers, trigger daemon action, authorize commit or PR metadata, open PRs, or establish federation consensus.
