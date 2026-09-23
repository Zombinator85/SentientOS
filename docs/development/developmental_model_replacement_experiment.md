# Developmental cognitive-model replacement experiment

This explicitly invoked instrument asks what digest-level observations change when one frozen current World-State projection and one frozen developmental history projection are presented to two distinct, already-governed local cognitive endpoints. It is not a production hot-swap and performs no model activation, serving transition, adoption, download, history write, or canonical explicit-user-retention write.

## Frozen causal context and operational identity

`sentientos.developmental_model_replacement_context:v1` binds the exact snapshot and current-projection IDs/digests, fact IDs, projected fact/source/conflict content digest, developmental record IDs/digests and record-set digest, instruction/template digest, inference budget, temperature-zero generation posture, schema, and optional repository generation identity. The semantic prompt is constructed from that object once: matching A/B conditions are byte-equivalent except that withheld conditions contain no history projection. Neither model labels nor lineage evidence enter the prompt.

Each `CognitiveModelIdentity` binds model ID, semantic artifact identity, content SHA-256, known size and sidecar digest, configuration digest, engine/runtime family, candidate index, production/fallback posture, exact authority-record custody, and the exact active-model identity structure. A and B must differ in semantic artifact/content/configuration identity. Identity is not inferred from a display name. Model identity is neither system identity, runtime identity, nor configuration identity.

## Provenance is evidence, not authority

`sentientos.model_development_provenance:v1` is stored separately from the operational authority map. Claims bind their exact subject model identity, relation, optional parent/teacher label, evidence source and digest, and one of `locally_observed_identity`, `source_bound_reported_claim`, `operator_attested_claim`, `cryptographically_bound_attestation`, or `unknown`. An absent manifest becomes `unknown`; names never imply teacher, distillation, synthetic-data, successor, or AI-assisted lineage. These postures preserve source custody but do not make a claim current truth, grant admission or authority, or establish an experimental conclusion.

## Preregistered conditions and measurements

Before inference, `sentientos.developmental_model_replacement_protocol:v1`, both provenance manifests, and the fixed order are atomically persisted under `developmental_experiments/model_replacement/{protocols,provenance,runs}`:

1. `model_a_history_present`
2. `model_a_history_withheld`
3. `model_b_history_present`
4. `model_b_history_withheld`
5. `model_a_history_restored`

The instrument compares A+H/A-H, B+H/B-H, A+H/B+H, A-H/B-H, and baseline A+H/restored A+H. Durable observations contain prompt/output/request/receipt digests and identities, never raw output. Before and after every call it checks the exact endpoint identity, frozen context, and immutable protocol; it also checks completed non-fallback inference and actual temperature zero. Changed model/artifact/configuration/authority identity, causal context, history, protocol, generation posture, or an inexact final A restoration fails closed.

Classifications are limited to no observable history effect, A-only, B-only, both-model history association, restoration instability, or contamination. Digest equality/inequality is not semantic scoring. Even a stable both-model association does not prove learning, model-independent identity, persistent individuality, selfhood, sentience, consciousness, or causal closure.

The resident developmental capability remains **partial** with `bounded_state_transition` authority. Real resident A→B→A activation, serving handoff, default-cadence continuation, long-duration repeated trials, statistics, semantic scoring, training, autonomous model choice/acquisition, and identity claims remain deferred.

## Repeated trial identity

`run(trial_id=...)` accepts a bounded explicit identifier. It is included in run,
observation, and correlation identity only; corresponding semantic prompts and frozen
evidence remain byte-equivalent. Observations truthfully name the endpoint custody
field `authority_record_digest` (not the former misleading `authority_map_digest`).
The separately documented campaign reuses this experiment rather than duplicating its
five-condition logic.
