# Selective memory distillation contract

The selective memory distillation contract is a deterministic, metadata-only
review layer for supplied memory-related records. It exists because raw logging
alone can drown SentientOS in fragments: every observation may be sensed, but not
every observation should remain equally salient forever. The contract evaluates
explicit JSON records into retain, distill, capsule, tomb-intent, protect, defer,
or reject decisions without touching runtime memory.

## Boundary doctrine

Distillation is not truth adjudication. Retaining a record means the metadata is
useful to keep or summarize; it does not prove the recorded claim is true.
Distillation is not memory mutation. The contract does not call
`memory_manager.py`, does not append memories, does not purge memories, does not
apply forgetting curves, and does not mutate vector indexes. Deletion
recommendation is not deletion: tomb decisions produce tomb intent metadata only,
and a later receipt/writer/verifier layer must perform and audit any real memory
write or deletion.

The contract also avoids prompt and authority surfaces. It does not assemble
prompts, retrieve live context, call providers, call network or GitHub APIs,
perform external disclosure, execute action ingress, or widen runtime authority.
Affective context remains descriptive and cannot imply consent. Embodiment
context remains descriptive and cannot admit work or execute action.
Authority/proof metadata remains non-authoritative and cannot become policy,
permission, or action.

## Relationship to memory systems

`memory_manager.py` already owns raw memory fragments, daily summaries, topic
capsules, turn summaries, session digests, vector metadata, tomb records,
curiosity reflections, glow highlights, importance scoring, access counts,
forgetting-curve pruning, purge/tomb mechanics, `summarize_memory`, and
`curate_memory`. This contract sits before any future writer layer as a pure
metadata evaluation step. It can say what a later layer may inspect, but it never
writes the distilled capsule or tomb receipt itself.

The context hygiene spine identifies Selector, Distiller, Pruner, and prompt
adapter/runtime middleware as deferred work. This contract formalizes the
Distiller/Pruner side only: raw telemetry is sensed, meaningful telemetry is
summarized, salient summaries may enter attention, attention may carry bounded
affective and embodied descriptors, retained memory may become compact symbolic
state, and tomb intent remains pending until a later audited receipt layer.

## AI-native capsules

AI-native capsules are compact, typed, deterministic, machine-digestible records.
They are allowed because some durable state is better represented as symbols
than prose, such as `need:...`, `affect:...`, `boundary:...`, `proof:...`,
`scope:...`, `authority:...`, `embodiment:...`, `retention:...`, and `next:...`.
Unlike human summaries, capsules are intentionally short and symbol-limited.
They must not contain raw private payloads, raw transcripts, images, audio,
video, screenshots, encoded media payloads, provider prompts, external secrets,
or policy grants.

Supported capsule types are `ai_symbolic_state`, `ai_boundary_state`,
`ai_affective_state`, `ai_embodiment_state`, `ai_authority_state`,
`ai_proof_state`, `ai_memory_digest`, `ai_task_handoff_state`,
`ai_operator_load_state`, `ai_future_work_state`, `ai_tomb_marker`, and
`ai_mixed_capsule`.

## Source records and decisions

Supported source record kinds are `raw_memory_fragment`, `observation_summary`,
`curiosity_reflection`, `action_reflection`, `context_hygiene_candidate`,
`affective_overlay`, `embodiment_proposal`, `embodiment_governance_bridge`,
`embodiment_action_ingress_validation`, `codex_task_report`,
`proof_bundle_summary`, `audit_summary`, `operator_note`, and the explicitly
controlled `unknown_record_kind`.

Supported decisions are `retain_raw_temporarily`, `distill_to_ai_capsule`,
`distill_to_human_summary`, `distill_to_dual_capsule`,
`merge_into_existing_capsule`, `protect_from_forgetting`,
`defer_for_operator_review`, `tomb_after_distillation`,
`tomb_without_retention`, `reject_record`, and `no_distillation_needed`.
Protecting from forgetting does not mutate memory. Merging into an existing
capsule does not write a merge. Tomb decisions require tomb intent metadata, and
tomb intent requires a later receipt/writer layer before any deletion can occur.

## Affective, embodiment, and governance context

The contract can preserve bounded affective descriptors from `affective_context.py`
and the 64-emotion matrix as descriptive metadata, for example a compact
`affect:hope=0.61+restlessness=0.34` symbol. Those descriptors never authorize
action or imply consent. Embodiment proposal, governance bridge, and action
 ingress validation references can be recorded as descriptive context, but they
cannot admit work, execute action, or bypass governance. Proof and authority
summaries can demonstrate review posture, but they remain non-authoritative.

## Lifecycle

The lifecycle is:

1. Raw telemetry is sensed by runtime systems.
2. Supplied metadata records are evaluated by this contract.
3. Valuable records may be summarized into human summaries, AI-native capsules,
   or dual capsules.
4. Low-value or superseded records may receive tomb intent metadata.
5. A future receipt/writer gate may write distilled capsules or tomb receipts.
6. A tomb receipt verifier may confirm that any deletion was separately audited.

Future sequence:

1. Selective memory distillation contract.
2. Distillation receipt/writer gate.
3. Tomb receipt verifier.
4. Self-improvement perception and affective ingress ledger.
5. GenesisForge embodied self-improvement handoff packet.
6. Governed local trial/proof/adoption loop.

## Non-authority guarantees

Every successful output states that retention is not truth, distillation is not a
memory write, distillation is not prompt assembly, a capsule is not policy, a
capsule is not authority, deletion recommendation is not deletion, external
disclosure is disabled, runtime memory mutation is disabled, prompt
materialization is disabled, and remote service behavior is disabled. Forbidden
next steps include immediate memory deletion or purge, memory writes, vector
index mutation, calls to memory-manager mutation/summarization APIs, prompt
assembly, live context retrieval, LLM/provider/network/GitHub calls, action
execution, inferring truth or authority from retention, converting capsules to
policy, converting distillation to action, bypassing context hygiene or memory
tombs, bypassing operator review, and enabling external disclosure.
