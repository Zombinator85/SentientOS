# Sequence 153 — Carry model-replacement scores into admitted history

**Source:** `0c51ac677b4a3b077bc22a7d30cccedc7a870a1a`  
**Tree:** `a35220fcc7d7462bfdac2b14233f53546e70f6cb`

A source review found that verified objective scores from the five-condition model-replacement experiment lost task/evaluator provenance before resident writeback. The experiment projection now emits a bounded score contract only when all five v3 task-family score rows share the same plan, task digest, schema, and evaluator, and their exact score-digest list agrees with the independently recomputed run evaluation. Digests are format checked.

The writeback projection independently validates that contract against the selected objective evaluation and canonical contract digest before preserving it. A prefix mismatch between the producer's `sha256:` digest and writeback's unprefixed helper had caused the valid contract to be dropped; the verifier now compares the correct canonical representation. Legacy/non-family records remain unchanged.

The integrated cognition test uses deterministic endpoints that answer from admitted family examples. It verifies the replacement score contract reaches World-State and is admitted through ordinary resident writeback as historical, non-current evidence, without exposing the fixture oracle's multiplier or offset. **One focused test passed**; the changed Python files compiled. This is hermetic fixture composition only, not actual model acquisition, transfer, or performance.

**Untested for production.** No hosted CI, typing, production, provider, or real-model behavior was verified.

Next: exercise restart reconstruction and duplicate projection for a scored model-replacement run, then verify the recovered contract remains eligible as historical later cognition without becoming fresh evidence. Real model custody and already-governed inference on the user's host remain external prerequisites.
