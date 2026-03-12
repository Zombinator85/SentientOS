---- MODULE AuditReanchor ----
EXTENDS Naturals, Sequences

VARIABLES historyState, breakVisible, checkpointExplicit, continuationDescends, degradedTrust

(* States: intact_trusted | broken_preserved | reanchored_continuation *)

Invariant_NoSilentRewrite ==
  \A s \in States: s.breakVisible => s.historyState # "intact_trusted"

Invariant_ContinuationRequiresAnchor ==
  \A s \in States: s.historyState = "reanchored_continuation" => s.checkpointExplicit /\ s.continuationDescends

Invariant_BreakVisibilityPersists ==
  \A s \in States: s.historyState = "reanchored_continuation" => s.breakVisible

Invariant_HealthyContinuationCoexistsWithPreservedBreak ==
  \A s \in States: s.historyState = "reanchored_continuation" => ~s.degradedTrust /\ s.breakVisible

====
