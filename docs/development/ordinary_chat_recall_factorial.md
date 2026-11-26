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
