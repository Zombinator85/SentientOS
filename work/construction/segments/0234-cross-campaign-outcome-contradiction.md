# Sequence 234 - Cross-campaign outcome contradiction

Campaign signals now retain the protocol's proposal identity as their bounded comparison scope. The signal plane compares only explicit target-outcome classes across that scope: repeated adverse outcomes remain consistent; a later matched positive result conflicts with the earlier adverse records. Both sides remain in the batch and receive blocked/manual-triage dispositions rather than being overwritten or silently preferred.

Repeated retrieval of the same result deduplicates deterministically. Confounded, interrupted/null, and insufficient-evidence records remain distinct and do not produce amendment proposals. A fresh Python process reconstructs the durable campaign classifications before evaluation.

Validation: 26 campaign, signal-plane, collector, selector, and candidate tests passed. Changed modules compiled, targeted candidate mypy passed, and `git diff --check` passed.

Next: extend the admitted runtime projection/recovery ordering tests, then continue Program B's later candidate-selection trajectory and the independent resource, epistemic, and goal-progress workstreams.
