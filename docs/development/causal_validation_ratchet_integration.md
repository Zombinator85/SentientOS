# Causal Validation Ratchet

Repository health and task regression are separate evidence axes.

- **Repository health** reports the failures present in the current run. It stays
  red when a proven pre-existing invariant failure remains.
- **Task regression** compares complete runs from an immutable reviewed base and
  the candidate, using the same command contract and materially equivalent
  environment. It is green only when the candidate has no new or increased
  normalized failure signature.

The comparison implementation is `sentientos.validation_causality`. The runner is
`python -m scripts.compare_validation_runs`. It records the immutable base SHA,
candidate SHA and workspace identity, exact argv digest, interpreter and package
environment identity, JUnit and run-provenance digests, and a normalized failure
multiset. `scripts.analyze_test_failures` supplies the shared JUnit parser;
`sentientos.forge_failures.semantic_failure_signature` supplies semantic identity.
File and line locations remain diagnostic and do not define failure identity.

The runner must execute both sides. An incomplete comparison cannot establish
non-regression or task causation. A strictly bound same-command, same-environment
paired timeout may be classified as `paired_timeout`, while its status remains
`comparison_incomplete`; the landing finalizer may then authorize only an exact
candidate commit for an already-required hosted substitute. Unclassified
incompleteness blocks. A mismatched immutable base, changed candidate workspace,
different command, or materially incomparable environment is invalid evidence. The
comparison artifact has schema `sentientos.validation_causality_comparison:v1`.
Its digest binds both run-provenance records and both normalized failure
multisets. The verifier recomputes the comparison before a finalizer may consume
it. A candidate-generated baseline is not accepted in place of the task-start
base.

The comparison distinguishes matched pre-existing failures, new failures,
retired/improved failures, changed signatures, and multiplicity changes. A new or
increased signature blocks. A matching signature can keep the task-regression
gate green while repository health remains red; this is visible debt, not a
waiver. Improvements retire debt. Incomplete evidence is indeterminate and
blocks attribution.

Exact task acceptance remains an independent gate: a required node must pass on
the candidate even if the same node also failed on the base. Protected-corridor
proof is independent from broad regression evidence and still blocks when its
required surface regresses. Environment-unavailable checks remain deferred only
under the existing hosted-validation contract; causal comparison does not make
them passed.

`sentientos.ci_baseline` now compares signature multisets rather than aggregate
failure counts. `scripts.emit_baseline_verification_status.py` reports
`repository_health_status` and `task_regression_status` separately. The landing
finalizer preserves raw broad-run evidence. It classifies candidate regression
only from complete differential evidence, preserves paired timeout as incomplete,
and treats unavailable stages as distinct from failed stages. Incomplete or
unavailable evidence never becomes a local pass. The finalizer remains the
repository landing authority; base/candidate execution provides evidence, not
landing authorization. Hosted validation must bind to the exact committed SHA and
tree before PR metadata or merge readiness.

For the current SentientMesh debt comparison, the reproducible command is:

```bash
python -m scripts.compare_validation_runs \
  --repository-root /tmp/SentientOS-hosted-validation-repair \
  --candidate-root /tmp/SentientOS-hosted-validation-repair \
  --base-sha 197e2a4ceeb13ab59a88fd531283355e15e1fd7d \
  --candidate-sha 197e2a4ceeb13ab59a88fd531283355e15e1fd7d \
  --node tests/test_sentient_autonomy.py::test_autonomy_generates_and_schedules_plans \
  --node tests/test_sentient_mesh_scheduler.py::test_weight_freeze_rejects_midcycle_trust_mutation \
  --output /tmp/causal-sentientmesh-comparison.json
```

The candidate SHA is the unchanged `HEAD`; its dirty workspace identity binds the
candidate edits. Use the same existing test environment for both sides. Do not edit
the SentientMesh implementation or tests to improve the task-regression result unless
differential evidence shows the candidate caused the failure.
