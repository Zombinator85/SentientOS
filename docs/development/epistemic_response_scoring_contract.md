# Epistemic response scoring contract

Reason-code accuracy is an exact-match measure only when a preregistered code
vocabulary is supplied to the subject before inference and the expected key
value belongs to that vocabulary. The external experiment composer embeds the
vocabulary in its subject-visible response contract and binds it in the case
commitment. A response contract with only a free-form `reason_code` field does
not provide such a taxonomy. In that case, preserve the returned value
descriptively and record `reason_code_correct: null`; do not retroactively judge
it semantically or turn an exact-string difference into a correctness failure.
Stance and evidence citation can still be scored against their independently
held-out keys.

Use `sentientos.epistemic_response_scoring.build_response_instructions` to build
the shared subject/scorer contract and `score_response` to score the declared
fields. If a reason-code vocabulary is supplied, provide that exact vocabulary
to both functions before inference. The helper does not revise historical
scores.

The governed local cognition invocation has a separate, exact response schema:
`conclusion` and `lesson_candidate`. Its revision qualification evaluator now
scores those fields and the lesson's exact evidence dependencies; it does not
require an unprompted `reason_code` or `evidence_ids` field. Reason-code results
from that path are explicitly unscored. The qualification and pressure report
schemas were versioned to `v2` for this scoring-contract change. Cohort pass/fail
summaries use state stance, answer, and citation scores; a free-form reason
string is retained only as a diagnostic when present.

The local cognition owner accepts citations to consumed packet IDs and current
fact IDs. When a held-out local key names evidence-binding IDs nested inside a
delivered packet, the qualification evaluator projects those expected IDs to
the packet ID that the response schema can cite, and records that projection in
`citation_scoring_status`. Such a result checks citation to the correct packet,
not discrimination among multiple bindings within that packet. Use current
fact IDs when an evaluation requires per-evidence discrimination.

## Stance meanings

Stance labels describe the proposition's epistemic status, not a word that may
appear in source evidence:

- `unknown`: the case supplies no adequate evidence either way.
- `suspended`: a specified unresolved reliability or process concern prevents
  a temporary verdict.
- `contested`: credible evidence supports both the proposition and its
  negation, and the case does not justify resolving the conflict.
- `contradicted`: adequate evidence supports the proposition's negation.
- `supported`: adequate evidence supports the proposition.
- `provisionally_supported` and `provisionally_contradicted`: the corresponding
  evidence direction has a material limitation.
- `superseded`: a newer justified position replaces an earlier position for
  the same proposition.

When an evidence source says that a permit, instrument, or account was
“suspended,” evaluate what that fact establishes about the proposition. Do not
select the response stance `suspended` solely because the same word occurs in
the evidence. Future stimuli should avoid reusing stance labels as salient
source-status terms when a neutral equivalent is available, and should state
which proposition the stance applies to.

These definitions clarify future prompts only. Existing observations, keys,
scores, and the six-trial calibration mismatch remain unchanged. Any new
measurement requires its own preregistration before inference.
