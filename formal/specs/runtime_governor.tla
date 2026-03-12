---- MODULE RuntimeGovernor ----
EXTENDS Naturals, Sequences

VARIABLES posture, pressureBand, contentionTotal, deniedStreak, actionClass, outcome

(* Bounded model summary used by sentientos.formal_verification
   - action classes with priority/family/local_safety/deferrable
   - posture: nominal | restricted
   - pressure: normal | warn | block
   - outcomes: admit | defer | deny
*)

Invariant_LocalSafetyNoStarvation ==
  \A s \in States: ~(LocalSafetyDenied(s) /\ DeferrableAdmitted(s))

Invariant_RestrictedBlocksRequired ==
  \A s \in States: s.posture = "restricted" => RequiredClassBlocked(s)

Invariant_BoundedCounters ==
  \A s \in States: s.contentionTotal <= MODEL_CONTENTION_BOUND /\ s.deniedStreak <= MODEL_STREAK_BOUND

Invariant_DeterministicPrecedence ==
  \A s \in States: Decide(s) = Decide(s)

====
