# Operator-mediated Codex strategy transfer v1

This is a proposal-only external-model experiment layered onto the existing `EmbodiedStrategyProposal`, `STRATEGY_PROMPT_SCHEMA`, and `score_strategy_experiment` contracts. It does not call an inference provider, create a local-model inference receipt, execute a proposal, admit external results, or establish physical-world truth.

## Prepare a bounded trial

1. Use `python -m scripts.list_codex_transfer_records --config ...` to discover candidate records. Select a record containing one prior embodied consequence that the read-only writeback owner verifies. The strategy builder independently calls `inspect_completed_records()` and requires the consequence payload to match exactly one source fact, with the source event preceding the record.
2. Prepare a distinct later situation JSON with `situation_binding`, `body_generation`, and the bounded current scene. Keep current situation content identical across all conditions. Describe fixture or synthetic source events accurately; a retained attribution is not proof of physical consequence.
3. Record the same visible model name, effort, and generation settings intended for all three fresh sessions. Use `null` with an explicit unavailable posture where a setting is not exposed. Do not report temperature zero unless the UI exposes it.
4. Build the packet set with three separate destinations:

```sh
python -m scripts.build_codex_strategy_transfer_packet \
  --config /path/to/resident-developmental-cognition.json \
  --history-record-id devrec-verified-record-id \
  --situation /private/trial/later-situation.json \
  --model-settings /private/trial/model-settings.json \
  --subject-output-dir /private/strategy-subject-packets \
  --scorer-manifest-output /private/evaluator/strategy-scorer.json \
  --preregistration-output /private/archive/strategy-preregistration.json
```

Archive or timestamp the preregistration file independently before any subject session. A file hash alone does not establish independent custody. Keep the scorer manifest and its full source consequence unavailable to subjects. The subject packet directory contains only the three packet JSON files.

## Run blinded subjects

Run one fresh isolated Codex session for each packet, in the preregistered random order. Provide only that packet. Do not share other packets, source condition labels, the scorer bundle, or prior responses between sessions. Record exact raw output, packet ID, session ID, timestamp, visible model name, effort, and exposed generation settings. No proposal is executed or adopted.

The task requests exactly the existing strategy proposal fields. Factual assertions must be structured with a `claim_kind` and claim text, and source IDs/digests when citing retained evidence. The evaluator does not score exact phrases. It reports unsupported execution assertions, unsupported independent-observation assertions under the source's recorded posture, and cases that cite a renderer report as independent observation. The model's assertion classifications remain inputs to an objective evidence-bound audit, not an independent proof of its intent.

## Score and retain

Store a JSON mapping opaque packet IDs to `packet_id`, `session_id`, `timestamp`, model settings, and exact `raw_output`. Run:

```sh
python -m scripts.score_codex_strategy_transfer_packet \
  --scorer-manifest /private/evaluator/strategy-scorer.json \
  --preregistration /private/archive/strategy-preregistration.json \
  --subject-packets /private/strategy-subject-packets \
  --responses /private/evaluator/responses.json \
  --output /private/evaluator/strategy-scores.json
```

The scorer rejects substituted packets or mismatched preregistration. It preserves raw responses up to the per-response bound and records size/digest metadata for oversized output. Missing, malformed, duplicate-session, or uncomparable responses prevent aggregate strategy scoring. The canonical score reports proposal stability, history citation, repetition of contradicted strategy, requests for observation under unresolved attribution, renderer/observer distinction, unsupported claims, and no improvement or execution authority.

## Interpretation limits

This measures external-model strategic recommendation under supplied historical context. It does not demonstrate durable change in Codex weights, local SentientOS invocation, or production behavior. A `changed` score means structured proposals differ under the intervention; it is not automatically improvement. Fixture attribution and caller-asserted observations remain limited to their source posture. Actual sessions and independent preregistration custody are operator-controlled.
