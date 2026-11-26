# Developmental-history scope clarification

This matched six-trial Hermes run tested whether explicitly distinguishing
developmental history from recent-turn transcript history changes use of
retrieved scored examples in ordinary chat.

The control and treatment used the same seed (42), source-near probes, structured
history presentation, model artifact, generation settings, strict JSON output
constraint, scored support record, and empty-history prompts. The treatment
replaced a redundant uncertainty sentence inside the developmental-history
guidance with a concise instruction to use DEVELOPMENTAL_HISTORY_DATA for
prior-practice questions and to reserve SESSION_HISTORY_DATA for recent turns.
This kept the history prompts below the 8,000-character limit. The comparison
verifies that the history block changed while the empty prompts and every
non-history prompt byte remained the same.

## Result

All six responses were valid strict JSON. Both control and treatment scored
0/9 exact answers in the history arm and 0/9 in the empty arm. The history
outputs were identical across conditions: [15, 16, 17] for near probes,
all-null for middle probes, and [20, 21, 22] for far probes. The two non-null
sets are wrong under the frozen 2x + 1 mapping. The empty arms abstained on
all probes.

The treatment changed neither answer payloads, strict-format validity, nor
accuracy. It therefore does not support the hypothesis that ambiguity between
the two history channels caused the earlier transfer failure. Because the
answer-only format does not expose the model's evidence recognition, this run
also cannot show whether the model noticed the selected record internally.
It establishes no learning, durable change, general transfer, or continuity.

## Files

- plan.json and frozen-plan.json: exact model-bound plan and prompt hashes.
- source-preflight.json: model-free task and evidence preflight.
- model-bound-preflight.json: confirms the frozen plan was prepared with no
  inference and zero resident VRAM.
- result.json and inference-receipts/: raw outputs and six governed receipts.
- independent-score.json: strict format and exact-answer scoring.
- history-scope-comparison.json: matched control validation and comparison.
- payload-diagnostic.json: descriptive payload extraction; it does not change
  official scores.
- source-reference.json and manifest.sha256: provenance and package hashes.

## Next diagnostic

Use a separately preregistered response schema that reports an evidence status
and cites the selected record ID alongside the answer. Score the evidence report
independently in history and empty arms. This can test whether Hermes recognizes
the history object before another transfer intervention is evaluated; a
self-reported citation remains behavioral evidence, not proof of internal use.
