# Sequence 233 - Route-qualified maintenance candidates

The existing maintenance candidate collector now respects the signal plane's classification and routing receipt. Only records with `candidate_identified=true` and a proposal disposition become candidates; diagnostic and blocked/contradicted signals stay out of later planning. Campaign-derived candidates preserve evidence references and proposal-only constraints, and carry low confidence while control-source issuers remain unverified. A fixture's authority ceiling was updated to admit its explicitly selected `test_failure` candidate kind.

The actual selected campaign result now traverses the admitted runtime signal plane into the existing maintenance candidate adapter with its result digest, source posture, and selection reference intact. This is a bounded proposal candidate handoff, not an authorized or executed task.

Validation: 19 collector, selector, and campaign-to-candidate tests passed. Both changed source modules pass targeted mypy; affected Python files compile and `git diff --check` passes. The closed-loop test remains an isolated fake Codex/local-repository fixture.

Next: exercise repeated campaign deduplication, contradictory observations, later correction, and cold reconstruction. Then build the Program B unsuccessful-improvement trajectory through a later candidate-selection episode, preserving the campaign's source uncertainty.
