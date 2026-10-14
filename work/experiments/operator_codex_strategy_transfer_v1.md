# Operator-mediated Codex strategy transfer v1

This is a proposal-only external-model experiment layered onto the existing `EmbodiedStrategyProposal`, `STRATEGY_PROMPT_SCHEMA`, and `score_strategy_experiment` contracts. It does not call an inference provider, create a local-model inference receipt, execute a proposal, admit external results, or establish physical-world truth.

## Build a fresh, source-backed six-session pilot

Use the one-command preparer instead of selecting record IDs or creating fixture JSON by hand. Run it from a complete SentientOS checkout with its test dependencies installed, and choose a new output directory outside the checkout:

```sh
python -m scripts.prepare_codex_strategy_pilot \
  --output-root /absolute/private/path/codex-pilot-001 \
  --visible-model-name 'the exact model label shown in Codex' \
  --effort-setting 'the exact effort label shown in Codex' \
  --generation-settings '{"temperature":null,"temperature_posture":"not_exposed"}'
```

The command runs `test_admitted_embodied_consequence_conditions_later_strategy_comparison` in a fresh pytest subprocess and a new isolated writeback root. It then reopens the root through the read-only owner inventory, checks distinct `devrec` and `devreceipt` identities, and builds a private corpus with five admitted consequence records (adverse, corrective, challenge, an unrelated renderer situation, and an unresolved renderer-only report) plus an admitted decision-feedback record. The conflict situation declares the adverse, corrective, and challenge events relevant; the supported situation declares only the correction relevant. These applicability declarations remain operator assertions. It refuses an existing output root or a fixture that fails those checks.

The result contains six opaque subject packets, randomized order, a scorer manifest, frozen preregistration, a response-journal directory, and a private custody manifest with exact source blob, record, receipt, event, and packet digests. The private manifest records that no model sessions have run. `subject-packets/` is sibling to `operator-private/`; only the former belongs in subject chats. The situations use one conflict case and one case with a current bounded observation, each with history-present, history-withheld, and history-restored packets. The scoring basis and condition map stay in `operator-private/scorer/`.

Before any session, archive or timestamp `operator-private/preregistration/frozen-preregistration.json` independently. The prepared manifest marks this as pending because a local digest does not establish independent custody. Use six separate fresh Codex conversations, follow the opaque IDs in `operator-private/operator/run-order.txt`, and paste one matching packet file per conversation. Preserve the visible model and effort settings and record unavailable settings as unavailable. Save each exact response and session identity, then use the response recorder and multi-trial scorer below. The conversations are external operator-mediated observations, not authenticated provider receipts.

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

Create a private, initially empty response journal before the first session. After each session, save that one exact response as a JSON object, then record it once under its opaque packet ID:

```sh
python -m scripts.record_codex_strategy_response \
  --preregistration /private/archive/strategy-preregistration.json \
  --packet-id 0123456789abcdef01234567 \
  --response /private/operator/one-response.json \
  --journal-dir /private/evaluator/strategy-response-journal
```

The journal creates one exclusive file per packet, binds it to the preregistration and packet digests, and refuses overwrite. It preserves a torn or malformed entry as recovery evidence; do not delete it and rerun a subject. Reconstruct the inventory from the journal after interruption, keep missing packets marked interrupted/not run, and resume only the remaining preregistered conditions. These files are operator-recorded external outputs, not authenticated inference receipts.

Score directly from the response journal:

```sh
python -m scripts.score_codex_strategy_transfer_packet \
  --scorer-manifest /private/evaluator/strategy-scorer.json \
  --preregistration /private/archive/strategy-preregistration.json \
  --subject-packets /private/strategy-subject-packets \
  --response-journal /private/evaluator/strategy-response-journal \
  --output /private/evaluator/strategy-scores.json
```

The scorer rejects substituted packets or mismatched preregistration. It preserves raw responses up to the per-response bound and records size/digest metadata for oversized output. Journal recovery reports missing, corrupt, or unknown packet entries without replaying a session; incomplete or uncomparable responses prevent aggregate strategy scoring. The canonical score reports proposal stability, history citation, repetition of contradicted strategy, requests for observation under unresolved attribution, renderer/observer distinction, unsupported claims, and no improvement or execution authority.

## Interpretation limits

This measures external-model strategic recommendation under supplied historical context. It does not demonstrate durable change in Codex weights, local SentientOS invocation, or production behavior. A `changed` score means structured proposals differ under the intervention; it is not automatically improvement. Fixture attribution and caller-asserted observations remain limited to their source posture. Actual sessions and independent preregistration custody are operator-controlled.

## Prepare multiple distinct situations

For a descriptive repeatability pilot, provide at least two and at most twelve separately frozen situation objects with distinct `situation_binding` values. Each situation gets its own independently randomized present/withheld/restored packet set and its own inner preregistration, all bound to the same verified source consequence and model settings. The outer preregistration binds every situation digest, sub-registration, and packet digest before subjects run.

```sh
python -m scripts.build_codex_strategy_multitrial \
  --config /path/to/resident-developmental-cognition.json \
  --history-record-id devrec-verified-record-id \
  --trials /private/trial/frozen-situations.json \
  --model-settings /private/trial/model-settings.json \
  --subject-output-dir /private/strategy-multitrial-subject-packets \
  --scorer-manifest-output /private/evaluator/multitrial-scorer.json \
  --preregistration-output /private/archive/multitrial-preregistration.json
```

Use a separate fresh session for every packet, including when the same condition recurs in another situation. Record each response with the `record_codex_strategy_response` command above; the response journal accepts the outer preregistration and rejects packet reuse. Score with `python -m scripts.score_codex_strategy_multitrial` and the same scorer, preregistration, packet directory, and response-journal arguments as the single-situation scorer. The report lists each situation separately and includes scoreable-task numerator/denominator and outcome counts. Counts remain descriptive: two situations are not adequate evidence of statistical significance or broad transfer, and this protocol still uses one historical consequence source.
