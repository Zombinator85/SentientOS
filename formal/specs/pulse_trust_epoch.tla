---- MODULE PulseTrustEpoch ----
EXTENDS Naturals, Sequences

VARIABLES activeEpoch, revokedEpochs, compromiseMode, classification, actionClass

Invariant_RevokedNeverTrustedCurrent ==
  \A s \in States: s.classification = "revoked_epoch" => ~TrustedCurrent(s)

Invariant_CompromiseModeTightens ==
  \A s \in States: s.compromiseMode => TightenedForRequiredActions(s)

Invariant_HistoricalDistinct ==
  \A s \in States: s.classification = "historical_closed_epoch" =>
      s.classification # "revoked_epoch" /\ s.classification # "unknown_epoch"

====
