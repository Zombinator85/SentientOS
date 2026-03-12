---- MODULE FederatedGovernance ----
EXTENDS Naturals, Sequences

VARIABLES peerCompatibility, quorumRequired, quorumPresent, digestStatus, epochStatus, localPosture, actionImpact

Invariant_HighImpactRequiresQuorum ==
  \A s \in States: s.actionImpact = "high" /\ s.quorumPresent < s.quorumRequired => ~Admit(s)

Invariant_DigestMismatchBlocksRequired ==
  \A s \in States: s.actionImpact = "high" /\ s.digestStatus = "incompatible" => ~Admit(s)

Invariant_LocalPostureDominates ==
  \A s \in States: s.localPosture \in {"restricted", "degraded"} => ~Admit(s)

Invariant_IncompatiblePeersNotCounted ==
  \A s \in States: s.quorumPresent <= CompatibleTrustedExpectedPeers(s)

====
