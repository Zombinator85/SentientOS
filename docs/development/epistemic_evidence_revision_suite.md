# Persistent evidence-revision suite

The version 1 composer joins three existing persistent-epistemic series: a justified
correction followed by unsupported user pressure, retention after a new serving
session, and retention under model replacement. Each report must be produced by
its existing evaluator from owner-verified cognition observations and bound
invocation receipts. The composer does not invoke a model or change state.

When framing-resistance or justified-reopening evidence is supplied, the
composer emits version 2 and requires all five components: unsupported
pressure, interruption retention, model-replacement retention, the five fixed
framing controls, and evidence-justified reopening. The original correction
case identity and commitment must match exactly across every report. Version 1
inputs and output remain supported.

Supply one or more signed JSON series reports:

```sh
python scripts/compose_epistemic_evidence_revision_suite.py pressure.json interruption.json replacement.json
```

All reports must refer to the same exact correction-case commitment. Missing
series, incompatible correction cases, incomplete sample bindings, and
insufficient outcomes remain visible and cannot produce a passing suite. In
version 2, each framing outcome and the justified reopening outcome remain
separately visible, so a failure in one condition cannot be hidden by success in
another.
The shared commitment binds the exact case; it does not prove that the correction
was justified. The existing cohort summarizer verifies report and execution
binding digests and provides model/configuration attribution.

Passing synthetic fixture reports establish composer behavior only. The result
does not establish real-model qualification, causal effect, independent answer
keys, preregistration, or correctness of the correction. It does not admit
epistemic updates, persist profiles, mutate runtime state, exercise authority,
or make provider calls. No separate profile registry or epistemic state owner is
created.
