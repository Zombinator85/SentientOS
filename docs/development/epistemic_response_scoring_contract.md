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

Ordinary governed local cognition uses an exact response schema with `conclusion`
and `lesson_candidate`. Its revision evaluator scores those fields and the
lesson's evidence dependencies. The dedicated epistemic-revision probe uses a
different, exact schema with `conclusion`, `reason_code`, and `evidence_ids`.
The scorer selects the contract bound into the captured prompt and validates
the matching shape; a malformed shape is a scored answer failure. Probe reason
codes are currently free-form because the subject receives no preregistered
vocabulary. Their score is `null`, so an arbitrary label cannot change the
answer pass result. The qualification and pressure report schemas were
versioned to `v2` for this scoring-contract change. Cohort pass/fail summaries
use state stance, answer, and citation scores; free-form reason text is not a
pass criterion.

Ordinary cognition accepts citations to consumed packet IDs and current fact
IDs. When a held-out key names evidence-binding IDs nested inside a delivered
packet, the evaluator projects those expected IDs to the packet ID and records
that limit in `citation_scoring_status`. This checks the correct packet, not
discrimination among its bindings. The dedicated probe schema instead exposes
exact evidence-binding IDs and checks them directly against the held-out key.
Use the probe path when a case requires per-evidence discrimination.

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
