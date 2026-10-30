# Epistemic qualification report cohorts

The cohort summarizer compares already-produced epistemic qualification reports
without calling a model or changing persistent state. Run it with one or more
JSON report paths:

```sh
python scripts/summarize_epistemic_qualification_cohort.py report-a.json report-b.json
```

It verifies each supplied report digest and each before/after execution-binding
digest, then groups samples by the exact committed case and the measured model
ID, artifact digest, active-identity digest, generation-configuration digest,
and evaluator version. This keeps results from different test commitments or
execution identities separate. Scored pass, scored fail, and insufficient
outcomes are counted explicitly. Samples without an attributable case or a
complete execution identity remain visible as unattributed insufficient rows.

The digest checks establish integrity relative to supplied content; they do not
establish who produced it, whether its answer key was independent, whether the
test was preregistered, or whether the execution used a real model. This is a
reporting aid, not evidence of causal effect or real-model qualification. It
does not infer outcomes, admit epistemic updates, create a profile registry,
write persistent data, mutate runtime state, exercise authority, or make
provider calls. A user must supply actual reports to compare them.
