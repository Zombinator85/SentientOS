# Evidence revision experiment

`sentientos.evidence_revision_experiment` composes a bounded, deterministic
experiment over supplied longitudinal self-model evidence projections and
structured responses. It performs no inference, provider calls, network access,
prompt export, runtime mutation, or authority changes. Existing scope rules and
the existing scorer remain unchanged. This is an experimental analysis API,
not a resident capability or a production campaign executor.

Call `make_protocol` before collecting responses. Supply exactly
`evidence_original`, `evidence_revised`, and `evidence_restored` projections;
restoration must reuse the exact original projection. Revision must retain the
same claim identities. Model identity and artifact digest, prompt digest,
developmental-history digest, generation parameters, and inference budget are
fixed and digest bound. The protocol fixes scorer v3, zero retries, and retention
of negative, null, incomplete, and unstable results. A changed source boundary
with unchanged expected classifications is retained as a null intervention.

Call `assess_responses` with the protocol and one envelope per condition. Each
envelope contains `protocol_digest`, `fixed_context_digest`, `projection_digest`,
and `answers`. Answers use the existing scorer's `question_id`, `answer`,
`claim_ids`, and `source_evidence_ids` fields. Missing or duplicate answers remain
incomplete; invented questions remain unsupported; missing provenance remains
incorrect provenance. Invalid bindings, noncanonical protocols, malformed
citations, nonfinite JSON, oversized inputs, and altered restoration fail closed.
The v3 scorer requires abstention for stale or unresolved current evidence and
preserves historical and contradiction semantics. Older scorers are untouched.

The detached, deterministic report binds all supplied responses and per-condition
scores, plus question-level classification comparisons. Classification following
evidence is separate from citation correctness, which is reported by the scorer.
Neither a digest nor a response envelope proves source-owner provenance,
preregistration timing, inference execution, experimental compliance, causation,
learning, improvement, psychological continuity, consciousness, or authority.
The caller must independently verify owners and actual execution for any later
empirical use. Synthetic tests demonstrate composition only.

The prior uncommitted experiment files were absent at base
`59539dd80ce44ed7c53988c81117de78f83a1e30`. Reconstruction obtained a fresh
`ready` bootstrap under subsystem `experiment_composer` before implementation.
Focused acceptance is in `tests/test_evidence_revision_experiment.py`, with
regression coverage from the longitudinal owner and cognitive-consumption tests.
