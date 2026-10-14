# Operator-mediated Codex transfer experiment v1

This protocol prepares controlled subject packets from canonical admitted developmental records. It performs no model inference and makes no provider request. The construction conversation is contaminated and must never be used as a subject session.

## Prepare

1. Run `python -m scripts.list_codex_transfer_records --config /path/to/resident-developmental-cognition.json` to inspect the privacy-bounded inventory. It reports canonical record/fact identities, digest and score lineage, example counts, probe identities/ranges, event and execution-evidence posture, and the read-only owner's admission verification. It omits observed answers and private oracle parameters. A family match does not establish a shared mapping; review applicability independently.
2. Select three distinct record IDs from configured developmental history: a positive record and an adverse record for the target family, plus an irrelevant record from a different family. Each record must contain source-score-bound admitted examples. The builder independently obtains records from the existing read-only writeback inventory, including runtime-admission verification, immutable receipt checks, record identity, and historical-only posture.
3. Freeze the mapping and held-out inputs before packet creation. Choose inputs absent from every source example. The operator must write a concrete applicability basis explaining why this target mapping is the same one represented by the source examples. The builder records this as operator-declared and unverified; a family label alone is not evidence of shared truth. It rejects source correctness labels that conflict with the declared shared mapping.
4. Write the exact visible Codex model name, effort setting, and generation settings to a private JSON file, for example:

```json
{
  "visible_model_name": "Codex model shown in session UI",
  "effort_setting": "medium",
  "generation_settings": {"temperature": null, "temperature_posture": "unavailable"}
}
```

5. Run `python -m scripts.build_codex_transfer_packet` with the three record IDs, family declarations, held-out inputs, private affine scoring parameters, and settings file. Supply three distinct output destinations: `--subject-output-dir`, `--scorer-output-dir`, and `--preregistration-output`. The builder rejects overlapping destinations. The subject directory contains only five packet files; the scorer directory contains the answer key and private nonce. Before the first subject session, archive or timestamp the preregistration artifact independently. Its hash alone is not proof of independent custody. Keep the scoring plan and scorer directory unavailable to subject sessions.

## Run blinded sessions

Open one fresh isolated Codex session per opaque packet ID. Paste only that packet's JSON content. The issued response contract is exactly one JSON object with an integer `answers` array and no additional text. Do not mention the treatment label or share other packets, the score manifest, scorer outputs, or this construction transcript. Record the session ID, timestamp, displayed model name, effort setting, generation settings, and exact raw output. Use the preregistered randomized order without telling subjects the order. Do not discuss outputs between sessions. Record unavailable model settings as unavailable; do not claim temperature zero when it is not exposed.

The five conditions are history present, history withheld, restored history, unrelated-family history, and adverse history. Present and restored carry identical source records/examples. Withheld carries an empty history. Packets expose only bounded source-fact provenance projections and the admitted historical examples; the original facts remain verifiable through record/fact identities and digests. Packets include no oracle parameters, answer key, or nonce.

## Score separately

Store raw responses in a scorer-only JSON mapping opaque packet IDs to `packet_id`, unique session ID, recorded settings, timestamp, and exact `raw_output`. Run `python -m scripts.score_codex_transfer_packet --scorer-manifest ... --preregistration ... --subject-packets ... --responses ... --output ...`. The scorer verifies preregistered packet hashes and treatment assignments before reporting exact probe correctness, full-task correctness, denominator, malformed/unscoreable outputs, and whether reported settings match preregistration. Retain raw outputs, preregistration, and score digest.

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
  --subject-output-dir /private/subject-packets \
  --scorer-output-dir /private/scorer-output \
  --preregistration-output /private/preregistration.json
```
