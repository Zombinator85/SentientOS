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

The same scorer was then run on three more completed source-near conditions,
plus a separate run with a frozen matched comparison for concise history
guidance. Across all five conditions, history and empty-history arms each
scored 0/9 exact answers, and each history-minus-empty difference was zero.
The scorer's tier counts matched the earlier independent scores in all five
reports.

| Condition | History exact | Empty exact | Strict JSON |
| --- | ---: | ---: | --- |
| Baseline | 0/9 | 0/9 | Valid in both arms |
| Rule derivation | 0/9 | 0/9 | History invalid at all three distances; empty valid |
| History-scope clarification | 0/9 | 0/9 | Valid in both arms |
| Record-linked rendering | 0/9 | 0/9 | Valid in both arms |
| Concise history guidance | 0/9 | 0/9 | Valid in both arms |

These are prompt-condition comparisons over the same model and source history,
not four independent replications. They show that the tested source-near
conditions did not produce exact transfer. The rule-derivation condition also
reduced response-format reliability in the history arm, so its answer score
should be read alongside that format failure. The corresponding new score
artifacts are `independent-score-codex-v2.json` within each run directory. The
v2 report also binds the scorer source and records the session and receipt IDs
for each arm/tier score.

For concise history guidance, the run's paired comparison confirms the history
block changed while the model, probes, scored support, empty prompts, output
constraint, and prompt text outside the history block matched. It still
produced no exact-answer or valid-format improvement. This is a single matched
pair, not a replicated intervention. See the [paired comparison](../../artifacts/experiments/ordinary-chat-retention-20261125/source-near-transfer-distance-ladder-hermes-prompt-guidance-v1/history-guidance-comparison.json)
and [receipt-bound rescore](../../artifacts/experiments/ordinary-chat-retention-20261125/source-near-transfer-distance-ladder-hermes-prompt-guidance-v1/independent-score-codex-v2.json).

The baseline and history-scope history arms returned the same answer payloads
at every distance. Record-linked rendering changed the guesses, but none
matched the fixed mapping. Rule derivation produced fenced JSON plus explanatory
text in all three history trials, which failed the strict JSON score. These
post-hoc output patterns suggest prompt presentation affected response
behavior, while none of the tested presentations yielded exact transfer.

## Next experiment: evidence-derived rule candidate

The repeated failures point to a narrower question: can a separate,
model-independent interpretation step make a rule latent in scored history
usable to later cognition? An opt-in projection fits an integer-affine
candidate only when at least three distinct inputs have evaluator-correct,
non-abstaining outputs and every listed row agrees exactly. It does not consult
the task-family answer-key registry. The packet records the fitted
coefficients and support range alongside the score-bound source rows.
Prompt assembly recomputes the fit and rejects a supplied candidate that
differs from those rows. Guidance labels it an unverified candidate and says
that predictions beyond the support range are extrapolations. The feature is
off by default and adds no history, authority, or memory mutation.

The earlier v8 design had three arms: raw scored rows (`history`), those same
rows plus the candidate (`derived_history`), and no history (`empty`). Its
derived-versus-raw contrast combined candidate content with adding a structured
candidate block.

The model-free [v9 sham-control preflight](../../artifacts/experiments/ordinary-chat-retention-20261125/source-near-transfer-distance-ladder-derived-affine-sham-preflight-v9.json)
adds `sham_history`, whose candidate is deterministically perturbed by one in
the offset while preserving its decimal width. It is explicitly marked
`sham_control`, recomputed from the same score-bound rows, and rejected if it
ever matches those observations. The primary contrast is now
derived-history versus sham-history; raw history and empty history remain
anchors. Candidate and sham prompts are both 7,961 characters with identical
history guidance and support rows; raw history is 7,829 characters. Their
serialized hypothesis objects are the same length. This controls prompt
character length for the primary contrast, but not tokenizer length or every
semantic effect of the provenance label.

There is a more specific label confound: the model-facing data identifies the
correct candidate as `task_derived` and the false candidate as `sham_control`,
and the shared guidance explains both labels. The derived-versus-sham result
therefore combines sensitivity to candidate content with sensitivity to the
experimenter's provenance labels. It cannot by itself show that the model
checked either candidate against the historical rows. Preserve v9 as the
label-informed baseline; do not reinterpret its contrast as blinded evidence
evaluation.

The next protocol revision should add a blinded candidate-content comparison.
Keep the true/sham assignment and exact source linkage in the frozen report,
but present both arms with the same neutral candidate label and identical
instruction that candidates are unverified and must be checked against the
listed score rows. The prompt-bound validator must still independently
recompute each candidate and retain the true/sham assignment outside the
model-visible prompt. Freeze prompt digests, answer-free probes, trial order,
and arm mapping before any response run. The primary contrast then asks
whether the model responds differently to a score-consistent candidate than
to a same-width false candidate when provenance labels cannot reveal the
answer. This would test evidence checking in the immediate task; it still
would not establish durable learning. A later-session test with the candidate
removed, fresh probes, and independent replication remains necessary.

The v9 report records the selected history record and state digest for each
arm, freezes a counterbalanced fixed trial order, and reconstructs exactly from
the same parent snapshot. It records `inference_performed: false` and
`learning_established: false`; no model-bound plan or response run exists yet.
The three tiers remain strata in one task, not independent replications. Even
a favorable derived-versus-sham score would not establish model learning,
correctness outside support, durability, or transfer across model replacement.

The three distance tiers are strata in one task experiment, not three
independent replications: they share one support record, task mapping, and
model. Report tier outcomes descriptively. A favorable one-run contrast would
motivate replication and longitudinal retention work; it would not establish
durable developmental learning.

The earlier [v3 preflight](../../artifacts/experiments/ordinary-chat-retention-20261125/source-near-transfer-distance-ladder-derived-affine-preflight-v3.json)
verified candidate projection but did not include a raw-history comparison,
so it cannot isolate the candidate's effect. The model-free
[v8 preflight](../../artifacts/experiments/ordinary-chat-retention-20261125/source-near-transfer-distance-ladder-derived-affine-preflight-v8.json)
freezes all three arms, their prompt bindings, the raw-versus-candidate primary
contrast, the trial order, and the exact runner/scorer implementation digests.
The prompt explicitly says that other rules may fit the same rows. It records
`inference_performed: false` and `learning_established: false`; a response run
and independent scoring remain future work. Hermes inference remains paused
while the GPU is in use.

The model-free [prompt exposure audit](../../artifacts/experiments/ordinary-chat-retention-20261125/source-near-transfer-distance-ladder-derived-affine-prompt-exposure-audit-v4.json)
checks that history guidance matches exactly, independently refits the
candidate from frozen scored rows, verifies its source linkage, and confirms
that raw and empty arms contain no candidate. It reports prompt character
counts by arm. The derived-history prompt is 92 characters longer than raw
history in each tier. Character count is not tokenizer length, so the current
contrast did not control for prompt-length effects. The v9 four-arm preflight
below adds a serialized-length-matched sham for its primary candidate contrast.
Rebuild this report with `python work/audit_ordinary_chat_transfer_prompt_exposure.py
<preflight.json> <audit.json>`. It stores a repository-relative input path and
binds both the frozen preflight and audit implementation by SHA-256, so the
report is reproducible from another working directory.

The audit also proposes a same-width negative-control hypothesis by changing
only the fitted offset by one, preserving the coefficient object's serialized
length while making it disagree with every support row. For this support, the
offset is 2 instead of 1. The v9 preflight includes this only as a
protocol-generated false candidate; it is not written back to history or
scored as evidence. Equal object length does not prove equal full-prompt token
length.

The retained v4 draft had the same arms but labeled history-versus-empty as
the primary outcome; v5 corrected that metadata. The v6 preflight added the
alternative-rule caveat and implementation-digest gate but left only seven
characters of prompt headroom. The v7 preflight keeps that caveat with shorter
guidance. The v8 preflight additionally gives raw and derived history the same
guidance, captures that text, and verifies it at run and score time. The v9
preflight adds the sham arm and makes derived-versus-sham the primary contrast.
A future response run still requires a reviewed model-bound plan and
independent scoring; Hermes/GPU inference remains paused while the GPU is in
use.
