# Sequence 232 - Verified campaign outcomes into governed signals

The maintenance runtime now joins its explicitly selected attribution campaigns to the existing improvement signal plane. It recovers each result and protocol through the read-only campaign owner before projecting a signal; arbitrary campaign-shaped JSON remains unsupported. Signal evidence carries result and campaign digests, classification, evaluation/control identities, reconstruction lineage, protocol selection identities, selection-config digest, original completion time, and the unverified control-source posture.

Positive and heterogeneous outcomes, interrupted trials, null results, and indeterminate results remain diagnostic-only. Confounded or insufficient measurements route as telemetry gaps. Supported adverse classifications remain reviewable proposal candidates. No effect, adoption, repository mutation, or provider authority was added.

Validation: 12 selected campaign, signal-plane, and admitted runtime nodes passed. The wider four-file run passed 53 tests and exposed five existing failures: three stale campaign expectations/signatures, one read-only `/glow` runtime setup failure, and one runtime admission fixture mismatch. Targeted mypy reports the existing repository baseline errors; none point to the new lines. Changed modules and tests compile; `git diff --check` passes.

Next: inspect the signal consumer and candidate-collection path to determine whether this routed evidence reaches a later bounded maintenance proposal with complete historical references and no authority promotion.
