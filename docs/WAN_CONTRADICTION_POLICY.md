# WAN Contradiction Policy

The WAN contradiction policy classifies truth-oracle evidence into deterministic classes:

- `no_contradiction`
- `expected_degradation`
- `explainable_divergence`
- `policy_blocked_but_coherent`
- `missing_evidence_nonblocking`
- `contradiction_warning`
- `contradiction_blocking`

## Evaluated contradiction dimensions

The policy evaluates at minimum:

1. quorum vs digest posture
2. epoch vs peer acceptance
3. replay expected-missing vs replay contradicted
4. reanchor continuation vs cluster trust posture
5. fairness/pressure vs cluster health outcomes
6. cluster final digest vs node-level claimed truth

The policy consumes existing WAN truth-oracle outputs (`dimensions`, `provenance`, and normalized contradiction rows) and never rewrites runtime state.

## Deterministic thresholds

Default profile thresholds:

- `max_missing_nonblocking=5`
- `max_warning_before_block=2`

Outcome mapping:

- `pass`: no warning/blocking contradictions
- `pass_with_degradation`: only degradable/missing-evidence outcomes within threshold
- `warning`: at least one warning contradiction
- `blocking_failure`: at least one blocking contradiction OR warnings exceed threshold
- `indeterminate`: missing evidence exceeds threshold without a direct block

All policy outputs are hashed (`gate_digest`) and emitted as artifacts for auditability.
