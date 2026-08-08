# Prospective discernment outcome review

This is a **judgment-evaluation instrument**, not a co-authorship declaration, an authority surface, or SentientOS memory. Its sequence is:

> prediction before outcome → immutable commitment → later evidence → review → longitudinal judgment record

`sentientos.discernment_commitment.v1` freezes a proposition, stance (including legitimate suspension), confidence where applicable, the source packet and evidence snapshot, objections, change conditions, explicitly supplied forecasts, moves, horizon, surfaces, and provenance. It does not infer concrete forecasts from packet prose. The source packet must predate the commitment.

`sentientos.discernment_outcome_evidence.v1` is separately appended after the commitment. It retains canonical evidence identities and provenance, bounded observed facts, prospectively named expected or disconfirming observations that were witnessed, ambiguity, change conditions, and horizon status. It does not claim universal truth and cannot rewrite the commitment.

`sentientos.discernment_outcome_review.v1` deterministically reports `supported`, `contradicted`, `mixed`, `indeterminate`, or `not_yet_observable` while embedding the verified commitment and outcome evidence. Optional later packets use the existing stance-preflight comparison to distinguish evidence-backed revision from unsupported reversal. Source identity is retained for audit but never changes classification.

Longitudinal reports keep confidence-band outcomes, revisions, suspensions, contradictions, objections, and move consequences as separate inspectable dimensions. There is deliberately no composite intelligence, trust, quality, sentience, or co-author score: judgment is multidimensional, while one optimization target would discard information and invite metric gaming.

## JSON-only CLI

Run `python scripts/discernment_outcome_review.py --root <external-custody> {commit,record-outcome,review,longitudinal,inspect}`. Creation commands consume JSON files and emit canonical JSON. `commit`, `record-outcome`, and `review` append with exclusive creation; `inspect` is read-only. `longitudinal` emits a report without adopting it. Custody is caller-configured and external to runtime memory.

Every artifact carries an all-false authority posture. None can execute work, mutate memory or goals, invoke maintenance, create Git state, publish, grant authority, or modify a source artifact.
