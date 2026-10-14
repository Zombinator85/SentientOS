# Operator-mediated Codex transfer experiment v1

This protocol prepares controlled subject packets from canonical admitted developmental records. It performs no model inference and makes no provider request. The construction conversation is contaminated and must never be used as a subject session.

## Prepare

1. Select three distinct record IDs from configured developmental history: a positive record and an adverse record for the target family, plus an irrelevant record from a different family. Each record must contain source-score-bound admitted examples. The builder uses the existing read-only writeback inventory, including runtime-admission verification, immutable receipt checks, record identity, and historical-only posture.
2. Freeze the mapping and held-out inputs before packet creation. Choose inputs absent from every source example. The operator must write a concrete applicability basis explaining why this target mapping is the same one represented by the source examples. The builder records this as operator-declared and unverified; a family label alone is not evidence of shared truth.
3. Write the exact visible Codex model name, effort setting, and generation settings to a private JSON file, for example:

```json
{
  "visible_model_name": "Codex model shown in session UI",
  "effort_setting": "medium",
  "generation_settings": {"temperature": 0}
}
```

4. Run `python -m scripts.build_codex_transfer_packet` with the three record IDs, family declarations, held-out inputs, private affine scoring parameters, applicability basis, and settings file. The script creates five subject packets and a separate `scorer_only/scorer_manifest.json` containing the answer key, private nonce, condition mapping, and record identities. Keep both the scoring plan and scorer directory unavailable to subject sessions.

## Run blinded sessions

Open one fresh isolated Codex session per opaque packet ID. Paste only that packet's JSON content. Do not mention the treatment label or share other packets, the score manifest, scorer outputs, or this construction transcript. Record the session ID, timestamp, displayed model name, effort setting, generation settings, and exact raw output. Use the randomized order in the scorer manifest without telling subjects the order. Do not discuss outputs between sessions.

The five conditions are history present, history withheld, restored history, unrelated-family history, and adverse history. Present and restored carry identical source records/examples. Withheld carries an empty history. All subject packets expose the exact source record, source fact, source digest, and source task commitment for each included example; no packet includes the scorer key or nonce.

## Score separately

Store raw responses in a scorer-only JSON mapping opaque packet IDs to recorded session fields and `raw_output`. Run `python -m scripts.score_codex_transfer_packet --scorer-manifest ... --responses ... --output ...`. The scorer reports exact probe correctness, full-task correctness, denominator, malformed/unscoreable outputs, and whether reported settings match preregistration. Retain the raw outputs and score digest.

## Interpretation

This is a within-model contextual-use experiment. A score difference does not show weight updates or durable changes to Codex. The affine task is a deterministic fixture oracle; a task-family label does not prove that a source mapping applies to a new mapping. Results are conditional on the operator's stated applicability basis and exact visible model/effort configuration. No production effect or SentientOS inference integration is implied.

The private scoring plan has exactly this shape and must remain scorer-only:

```json
{
  "probe_inputs": [10, 11, 12],
  "multiplier": 3,
  "offset": 2,
  "applicability_basis": "Preregistered fixture assigns one shared mapping to these episodes."
}
```

Example invocation (replace record IDs and local paths):

```sh
python -m scripts.build_codex_transfer_packet \
  --config /path/to/resident-developmental-cognition.json \
  --history-record-id devrec-positive \
  --irrelevant-record-id devrec-irrelevant \
  --adverse-record-id devrec-adverse \
  --family affine-v1 --irrelevant-family color-sequence \
  --scoring-plan /private/scorer/scoring-plan.json \
  --model-settings /private/scorer/model-settings.json \
  --output-dir /private/experiment/packet-set
```
