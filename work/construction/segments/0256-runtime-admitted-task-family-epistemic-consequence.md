# Sequence 256 - Runtime-admitted task-family epistemic consequence

The epistemic development runtime now accepts an exact, owner-recovered scored task-family run through an explicitly configured proposition rule. The experiment store determines support, contradiction, or contextual relation from its frozen condition scores. The runtime validates family/proposition scope, binds the run digest and event time to a source proof, and obtains separate admissions for evidence append and state update through the existing mutation controller. Scored ties remain contextual evidence without a directional state change. Reprocessing an already applied run does not duplicate the update.

The interrupted-run recovery test now exercises this route instead of directly calling the persistent epistemic owner's mutation methods. It rejects a wrong run digest before admission, verifies both mutation receipts after owner reconstruction, carries the exact state digest into a later cognition prompt, and reads the live epistemic owner through causal introspection. Introspection reports bounded state and binding counts plus mutation recovery health; it does not claim the fixture score proves a cause or external truth.

Validation: affected epistemic development, mutation, developmental experiment, and resident cognition suites passed. The focused causal-introspection and epistemic runtime scope passed (57 tests). Changed Python files compiled and whitespace checks passed.

Limits: this is a deterministic fixture outcome with unresolved evidence dependency and freshness. Causal introspection currently exposes owner-level metadata rather than the exact per-proposition consequence chain. Later negative-transfer correction and outcome-informed goal planning remain queued.
