# Codex Workcell Storage Consent Design Evidence Map

This page is a navigation aid for the existing storage-policy and operator-consent
design documents. It adds no contract, consent stage, verifier result, or runtime
behavior. Read each linked contract for its canonical requirements and each
verifier for the checks it performs.

## How to read the document set

The documents describe separate metadata-only boundaries. Their arrangement here
helps locate related material; it is not an authorization sequence. A packet,
report, complete dossier, or successful structural verification does not prove
that a request was presented, that an operator responded, or that consent exists.
Active `/ledger` writes and `/glow` archives remain blocked by the existing
contracts.

| Concern | Contract or evidence | Verifier | What the pair covers |
| --- | --- | --- | --- |
| Storage policy | [Storage policy contract](codex_workcell_storage_policy_contract.md) | [Storage policy verifier](codex_workcell_storage_policy_verifier.md) | Future storage paths, retention, digest, parent-chain, and vow-binding rules. |
| Dry-run transaction | [Storage transaction plan](codex_workcell_storage_transaction_plan.md) | [Storage transaction plan verifier](codex_workcell_storage_transaction_plan_verifier.md) | Proposed `/ledger` and `/glow` effects as metadata; no writes or archives. |
| Execution review | [Storage execution dossier](codex_workcell_storage_execution_dossier.md) | [Storage execution dossier verifier](codex_workcell_storage_execution_dossier_verifier.md) | Supplied execution-design evidence and unresolved authority gaps. |
| Runtime boundary | [Storage runtime authority contract](codex_workcell_storage_runtime_authority_contract.md) | [Storage runtime authority verifier](codex_workcell_storage_runtime_authority_verifier.md) | Future runtime bindings and the reasons active storage remains blocked. |
| Request shape | [Operator consent request contract](codex_workcell_storage_operator_consent_contract.md) | [Request contract verifier](codex_workcell_storage_operator_consent_verifier.md) | Future request fields, scope, digest bindings, lifetime, revocation, and denial rules. |
| Request packet | [Operator consent request packet](codex_workcell_storage_operator_consent_request_packet.md) | [Request packet verifier](codex_workcell_storage_operator_consent_request_packet_verifier.md) | A metadata packet assembled from supplied evidence; it does not present a request. |
| Presentation boundary | [Request presentation contract](codex_workcell_storage_operator_consent_request_presentation_contract.md) | [Presentation verifier](codex_workcell_storage_operator_consent_request_presentation_verifier.md) | Why packet existence and verifier success do not prove operator-facing presentation. |
| Response shape | [Consent response contract](codex_workcell_storage_operator_consent_response_contract.md) | [Response verifier](codex_workcell_storage_operator_consent_response_verifier.md) | The future explicit response schema; neither file creates or collects a response. |
| Evidence inventory | [Consent evidence dossier](codex_workcell_storage_operator_consent_evidence_dossier.md) | [Dossier verifier](codex_workcell_storage_operator_consent_evidence_dossier_verifier.md) | Inventory and structural review of design reports while real-world consent gaps remain open. |

## Interpretation limits

- The request, packet, presentation, response, and dossier documents describe
  distinct metadata boundaries. They do not form an executable ladder or grant
  authority to one another.
- Verifier statuses describe structure only. They are not consent, presentation,
  readiness, runtime binding, commit or PR authority, or permission to activate
  storage.
- The evidence dossier can report complete consent-design inputs while still
  reporting that presentation, an operator response, signature, and active writer
  authority are missing.
- Any future active-storage behavior requires a separately governed authority
  contract and implementation. This index does not supply either.

For the broader workcell storage model, see the
[Codex Workcell Memory Contract](codex_workcell_memory_contract.md),
[Storage Runtime Authority Boundary Contract](codex_workcell_storage_runtime_authority_contract.md),
and [Codex Open-Work Roadmap Index](codex_open_work_roadmap_index.md).
