# Held-out source-near presentation replication

Three matched Hermes pairs tested whether record-linked history presentation changes transfer on probes not used in the prior seed 42/101/202 presentation replication or the saved parent history.

- Seeds: [303, 404, 505]
- Probes: near 13/17/22; middle 24/25/26; far 27/28/29
- Model manifest: f6a766d405cbb73f9ba64a59b8fb29a3418d0da0b6fad15a0ca70687413ce0ce
- Strict JSON validity: structured-only 17/18, record-linked 16/18
- History exact answers: 0/27 structured-only and 0/27 record-linked
- Empty exact answers: 1/27 in both presentations

The only exact answer was from the empty arm at seed 505: input 25 -> 51, correct under the frozen 2x + 1 mapping. Neither history presentation scored a correct answer. Record-linked rendering changed answer payloads in all three seed pairs. Seed 505 had one invalid strict-JSON response in structured-only history and two in record-linked history; the raw text adds explanatory prose after a fenced JSON object. The other seeds had valid strict JSON in all six trials.

This follow-up does not reproduce the prior seed 101 history hit on fresh probes. It indicates that presentation changes immediate responses, but gives no evidence of history-caused accuracy gains on this held-out set. It does not establish durable learning or general transfer.

Each seed includes six model-free and two model-bound preflights, six full plans/results, independent scores, paired comparisons, and 12 separate governed receipts. The isolated Ollama server on 11436 was stopped; the unrelated 11434 listener was left untouched.


Lenient payload diagnostics are included beside each independent score. They recover one fenced JSON object only for diagnosis; the official strict scorer remains unchanged. The three seed 505 history outputs that failed strict JSON were all recoverable, but each recovered answer list was all null and scored 0/3. Thus the format failures hid no correct history answer. The empty arm's single 1/27 hit was valid strict JSON and remained the same under both history presentations.
