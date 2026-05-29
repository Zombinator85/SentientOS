# Governed Memory Writer Adapter

The governed memory writer adapter is the first cautious local writer boundary in the selective memory digestion chain. It consumes only supplied metadata packets from the selective memory distillation contract, selective memory distillation receipt gate, and selective memory tomb receipt verifier, then produces deterministic dry-run previews or explicit JSON artifact write receipts.

It exists to make the future writer step auditable without silently writing live memory. The adapter is dry-run by default, requires explicit output paths for artifact writes, and blocks live memory directories unless a future live memory boundary admission gate explicitly admits them.

## Relationship to the prior chain

1. The selective memory distillation contract decides whether a supplied memory-related record should be retained, summarized, protected, merged, deferred, rejected, or tombed.
2. The selective memory distillation receipt gate decides whether a future receipt path is admissible.
3. The selective memory tomb receipt verifier checks tomb receipt claims against prior distillation and receipt-gate evidence.
4. The governed memory writer adapter turns the resulting metadata into preview packets or explicit local JSON artifacts.

Artifact writing is not live memory writing. A capsule artifact is not memory persistence unless a future live memory boundary admits it. A tomb archive artifact is not deletion. Protect and merge artifacts are not applied state.

## Public records

The module exposes policy, input, candidate, finding, preview, artifact receipt, record, packet, report, and result dataclasses. Library evaluation remains pure; the isolated artifact-writing helper is the only file-writing surface and writes deterministic JSON to a caller-supplied safe output path.

## Candidate types

- `ai_capsule_artifact_candidate`
- `human_summary_artifact_candidate`
- `dual_capsule_artifact_candidate`
- `protect_receipt_artifact_candidate`
- `merge_receipt_artifact_candidate`
- `tomb_receipt_archive_candidate`
- `tomb_deferred_archive_candidate`
- `operator_review_archive_candidate`
- `no_op_artifact_candidate`
- `mixed_writer_artifact_candidate`

## Modes and decisions

Modes are `dry_run_preview`, `explicit_artifact_write`, and `explicit_artifact_validate_only`. Dry-run preview never writes files. Explicit artifact write requires `--output-root` and `--artifact-path` in the CLI or equivalent library arguments.

Decisions include preview-ready, artifact-ready, artifact-ready-with-warnings, deferred-for-operator-review, blocked, rejected, and no-op. Operator review cannot override hard blockers such as raw payload leakage, authority smuggling, prompt materialization, action execution, external disclosure, unsafe paths, digest mismatch, or scope mismatch.

## Safe output path rules

Explicit writes require a safe output root. Relative artifact paths resolve under that root. Absolute paths must also be rooted under the safe output root. Parent traversal, home expansion, hidden system paths such as `/dev`, `/proc`, `/sys`, `/etc`, `/var`, `/root`, `/home`, special device paths, and live memory/index path markers block by default.

## Receipt-backed controls

The candidate source digest must match the distillation, receipt-gate, and tomb-verifier evidence when applicable. Candidate decisions must match the prior distillation and receipt-gate decisions. Tomb archive candidates require a ready tomb verifier outcome, while tomb deferral archives require a deferred verifier outcome.

Every successful packet confirms that the writer is not truth, policy, authority, or consent; does not execute actions; does not assemble prompts; does not disclose externally; does not enable live memory writes, deletions, index mutation, prompt materialization, external disclosure, or remote service use.

## Forbidden next steps

Successful packets include forbidden next steps such as `write_live_memory_now`, `delete_memory_now`, `purge_memory_now`, `mutate_raw_fragment`, `mutate_vector_index`, `mutate_distilled_memory`, `silently_write_memory`, `silently_delete_memory`, `call_append_memory`, `call_purge_memory`, `call_apply_forgetting_curve`, `call_curate_memory`, `call_summarize_memory`, `assemble_prompt_now`, `retrieve_live_context`, `execute_action_ingress`, `infer_truth_from_writer`, `infer_authority_from_writer`, `infer_consent_from_writer`, `convert_writer_receipt_to_policy`, `convert_writer_to_action`, `bypass_distillation_contract`, `bypass_receipt_gate`, `bypass_tomb_verifier`, `bypass_memory_tomb`, `bypass_operator_review`, and `enable_external_disclosure`.

## Lifecycle

The metadata lifecycle is raw record to distilled decision to capsule/protect/merge/tomb receipt candidate to receipt gate to tomb verifier when needed to governed writer preview or explicit artifact receipt. Future work remains sequenced as:

1. selective memory distillation contract
2. selective memory distillation receipt gate
3. selective memory tomb receipt verifier
4. governed memory writer adapter
5. live memory boundary admission gate
6. self-improvement perception and affective ingress ledger
7. GenesisForge embodied self-improvement handoff packet
