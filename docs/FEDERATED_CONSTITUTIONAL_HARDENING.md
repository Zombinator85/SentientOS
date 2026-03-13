# Federated Constitutional Hardening

This pass hardens SentientOS from single-node constitutional runtime semantics to federation-ready control-plane semantics while preserving startup-only GenesisForge expansion boundaries.

## What was added
- Pulse key epoching/rotation artifacts and CLI (`glow/contracts/pulse_key_epoch_status.json`, `glow/contracts/pulse_key_rotation_report.json`).
- Subject-level RuntimeGovernor fairness with bounded state cap and deterministic subject normalization.
- Federated quorum classes + quorum decision/status artifacts (`glow/federation/quorum_status.json`, `glow/federation/quorum_decisions.jsonl`).
- Governance digest mismatch reporting (`glow/federation/governance_digest_mismatch_report.json`).
- Repair outcome verification lifecycle artifacts (`glow/repairs/repair_outcomes.jsonl`, timestamped outcome report files).

## Rollout modes
- Fairness: shadow/advisory/enforce via RuntimeGovernor mode and fairness instrumentation.
- Quorum/digest: deterministic enforcement for high-impact controls; low-impact observation remains allowed.
- Repair verification: enabled by default; can be disabled with `SENTIENTOS_REPAIR_VERIFY=0`.

## Local 2-node federation
Small home federation deployments use the same digest and quorum semantics as larger federations; thresholds remain configurable via environment variables.
