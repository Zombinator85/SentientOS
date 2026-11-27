# Ordinary chat recall: factorial Hermes pilot

## Verified result

The captured 2×2 pilot crosses explicit history-row mapping guidance with a
strict cited-JSON response instruction. It reuses one fixed set of eight
ordinary-chat recall conditions across four arms. The preflight held model,
runtime, source-history evidence, tasks, and generation settings constant;
only the two named prompt factors changed.

| Arm | Official exact | Official valid format | Fenced content exact* | Fenced content and citation exact* |
| --- | ---: | ---: | ---: | ---: |
| Neither factor | 0/8 | 0/8 | 2/8 | 2/8 |
| Row mapping only | 0/8 | 0/8 | 7/8 | 7/8 |
| Strict output only | 4/8 | 6/8 | 5/8 | 4/8 |
| Both factors | 5/8 | 6/8 | 6/8 | 5/8 |

\* The fenced-payload measures are post-hoc diagnostics. The preregistered
full-response score remains primary.

Across the two no-strict-output arms, official exact accuracy was 0/16. With
the strict output instruction it was 9/16, and valid-format responses rose
from 0/16 to 12/16. Row-mapping guidance changed official exact accuracy by
0/16 without the strict output instruction and by 1/16 with it. In the
post-hoc fenced-payload diagnostic, mapping guidance raised exact content
plus citation from 2/16 to 7/16 without strict output and from 4/16 to 5/16
with strict output.

These are descriptive counts over eight repeated conditions per arm. The
conditions are not independent replications, and no significance claim is
supported. The result indicates that ordinary-chat history can supply useful
rows to a response, while the unstructured response path often fails the
strict scorer. It does not show that the history changed the model's durable
capabilities: this is a same-session prompt intervention, not a later-session
held-out test after the mapping instruction is removed.

## Evidence and reproduction

The result package is
[`cuda-hermes-recall-factorial-full-v2`](../../artifacts/experiments/ordinary-chat-retention-20261125/cuda-hermes-recall-factorial-full-v2/).
Its `run-manifest.json` records four completed arms with inference performed
and `learning_established: false`. The independent verifier rechecked the
frozen arm plans, source-history match, capture checksums, and response scores;
it reported `all_arms_independently_verified`. Its bound model is
`sentientos-hermes4:14b-q4km`, content SHA-256
`f6a766d405cbb73f9ba64a59b8fb29a3418d0da0b6fad15a0ca70687413ce0ce`, with 24
GPU layers requested. The output diagnostic rederived fenced JSON content,
citation, and outside-fence prose from the captured responses. These checks
verify the records and scoring, not the interpretation as learning.

From the repository root, rerun the CPU-only verification and diagnostic with:

```powershell
python -m work.verify_sibling_chat_recall_factorial_run artifacts/experiments/ordinary-chat-retention-20261125/cuda-hermes-recall-factorial-full-v2
python -m work.analyze_sibling_chat_recall_factorial_outputs artifacts/experiments/ordinary-chat-retention-20261125/cuda-hermes-recall-factorial-full-v2
```

## Next developmental evidence

The next test should use fresh held-out conversation records and probes, then
query in a later session without row-mapping guidance. Keep a matched empty or
withheld-history control and an independently scored outcome. That design
would test whether ordinary-chat experience itself supports transfer after
the immediate prompt aid is gone. Until such a test succeeds and is
replicated, retain the conclusion that durable learning is unestablished.

## Frozen transfer ladder scorer

`work/score_ordinary_chat_transfer_distance_ladder.py` provides a CPU-only
scoring boundary for the actual runner output. It takes a v1 or v2 model-free
preflight and a completed run directory. It checks that the plan binds to the
provided preflight, verifies each tier's answer-key commitment against the
task-family mapping, checks fixed prompt bindings and trial order, and binds
each output to a unique fresh session and governed receipt. The runner now
records each session ID in its trial result. The scorer reports exact answers
per tier for the history and empty-history arms and their difference.

Run it from the repository root with:

```powershell
python -m work.score_ordinary_chat_transfer_distance_ladder preflight.json run-directory score.json
```

The output explicitly records `learning_established: false`. Scoring a
receipt-bound execution validates record integrity and immediate transfer
performance; it does not establish durable learning, independent replication,
or causal attribution to how the source history was acquired. No model
execution is part of this scoring step.

### Existing source-near run

The integrated scorer was exercised against the completed
`source-near-transfer-distance-ladder-hermes-history-scope-v1` run and its
bound `source-near-transfer-distance-ladder-history-scope-preflight-v2.json`.
It recovered each fresh session ID from the governed receipt because this
older run predates storing the ID in its aggregate trial row. All six session
IDs were distinct, and the scorer checked each receipt against the plan's
prompt digest, model identity, and returned output.

| Distance | History exact | Empty exact | Difference | Valid JSON in both arms |
| --- | ---: | ---: | ---: | --- |
| Near | 0/3 | 0/3 | 0 | Yes |
| Middle | 0/3 | 0/3 | 0 | Yes |
| Far | 0/3 | 0/3 | 0 | Yes |

The earlier independent score for this run reports the same counts. This is a
floor-effect result: the history arm showed no transfer advantage in this
model and prompt condition, while the empty arm also failed every answer. It
does not establish that developmental learning is absent in general. The
rescored artifact is
[`independent-score-codex-v2.json`](../../artifacts/experiments/ordinary-chat-retention-20261125/source-near-transfer-distance-ladder-hermes-history-scope-v1/independent-score-codex-v2.json);
it records the bound plan and preflight digests and keeps
`learning_established: false`.

The same scorer was then run on three more completed source-near conditions.
In all four conditions, history and empty-history arms each scored 0/9 exact
answers, and each history-minus-empty difference was zero. The scorer's tier
counts matched the run's earlier independent score in all four cases.

| Condition | History exact | Empty exact | Strict JSON |
| --- | ---: | ---: | --- |
| Baseline | 0/9 | 0/9 | Valid in both arms |
| Rule derivation | 0/9 | 0/9 | History invalid at all three distances; empty valid |
| History-scope clarification | 0/9 | 0/9 | Valid in both arms |
| Record-linked rendering | 0/9 | 0/9 | Valid in both arms |

These are prompt-condition comparisons over the same model and source history,
not four independent replications. They show that the tested source-near
conditions did not produce exact transfer. The rule-derivation condition also
reduced response-format reliability in the history arm, so its answer score
should be read alongside that format failure. The corresponding new score
artifacts are `independent-score-codex-v2.json` within each run directory. The
v2 report also binds the scorer source and records the session and receipt IDs
for each arm/tier score.

The baseline and history-scope history arms returned the same answer payloads
at every distance. Record-linked rendering changed the guesses, but none
matched the fixed mapping. Rule derivation produced fenced JSON plus explanatory
text in all three history trials, which failed the strict JSON score. These
post-hoc output patterns suggest prompt presentation affected response
behavior, while none of the tested presentations yielded exact transfer.
