# Federated Quorum + Governance Digest Hardening

## Scope
This hardening pass introduces deterministic, auditable federation gating for sensitive operations, especially `restart_daemon` control events.

## Model

### 1) Governance digest
Each node computes a compact governance digest from deterministic components:
- immutable manifest identity + sha256
- invariant policy identity + sha256
- audit trust posture (including degraded/re-anchor-required state)
- pulse trust epoch state (active epoch, revoked epochs, compromise mode)
- runtime governor posture inputs relevant to federated restriction

Artifacts:
- `/glow/governor/governance_digest.json`
- `/glow/federation/governance_digest.json`

### 2) Peer digest compatibility
Inbound federated events can carry `governance_digest`.
The evaluator classifies peers as:
- `exact_match`
- `compatible_family`
- `patch_drift`
- `epoch_mismatch`
- `incompatible`
- `locally_restricted`

Digest mismatch reasons are explicit and deterministic (`*_mismatch` keys).

### 3) Quorum classes
Deterministic quorum classes:
- `low_impact_advisory`: advisory/telemetry (single trusted peer)
- `medium_impact_coordination`: coordination (configurable quorum)
- `high_impact_control`: sensitive control (`restart_daemon`, lineage/trust-affecting operations)

High-impact defaults to quorum `>=2` compatible trusted peers.

Artifacts:
- `/glow/governor/federation_quorum_policy.json`
- `/glow/federation/federation_quorum_policy.json`
- `/glow/governor/federation_quorum_decisions.jsonl`
- `/glow/federation/federation_quorum_decisions.jsonl`
- `/glow/governor/peer_governance_digests.json`
- `/glow/federation/peer_governance_digests.json`

## Integration points
- `sentientos/daemons/pulse_federation.py`
  - trusted peer registry now feeds quorum evaluator
  - inbound events use embedded governance digests when present and persist peer digest state for audit
  - inbound events get digest/quorum evaluation before sensitive action admission
- `sentientos/runtime_governor.py`
  - federated governance posture dimension added
  - digest/quorum/epoch mismatch reasons can block federated control deterministically
- governor state and budget artifacts include federation governance digest

### 3) Pulse protocol compatibility contract

Federated pulse events now carry an explicit `pulse_protocol` claim with:
- protocol semver (`protocol_version`)
- schema family + required/default field contract
- signing expectations
- replay policy contract (`policy_version`, window, tolerance)
- deterministic `protocol_fingerprint`

Compatibility is explicit and machine-classified:
- `exact_protocol_match`
- `compatible_family`
- `patch_compatible`
- `deprecated_but_accepted`
- `incompatible_protocol`

### 4) Replay-window harmonization

Replay admission now differentiates:
- `peer_within_compatible_replay_horizon`
- `peer_outside_accepted_replay_horizon` (signed but dropped for control significance)
- `peer_too_stale_for_replay_horizon`
- `incompatible_replay_policy`

### 5) Anti-equivocation evidence

Bounded windows detect and persist:
- `confirmed_equivocation` (same correlation with conflicting signed hashes)
- `protocol_claim_conflict`
- `replay_claim_conflict`
- `weak_equivocation_signal` (digest posture conflict)
- `no_equivocation_evidence`

Artifacts:
- `/glow/federation/equivocation_evidence.jsonl`
- `/glow/federation/equivocation_summary.json`
- `/glow/federation/pulse_protocol_posture.json`

## Federation ingest replay suppression

Federated pulse ingest uses deterministic event identity (`event_hash` over
canonical payload) with a bounded replay cache. Duplicate/replayed ingress is
classified explicitly as `suppressed_replay` and does not enter normal pulse
dispatch/history flows.

Classification artifact:

- `/glow/federation/ingest_classifications.jsonl`

## Deterministic denial semantics
Federated denial now distinguishes:
- trust epoch mismatch (`trust_epoch`)
- governance digest mismatch (`digest_mismatch`)
- insufficient quorum (`quorum_failure`)
- untrusted peer (`untrusted_peer`)
- peer restricted by local trust posture (`peer_trust_restricted`)
- local posture restriction (e.g., storm/pressure/audit posture) remains authoritative

## Remaining blind spots
- Quorum currently accumulates within bounded in-memory action keys per process lifecycle and is not persisted across restarts.
- Equivocation evidence is deterministic and bounded but local-to-node; there is no federated multi-party notarization exchange in this pass.
- Replay harmonization is explicit at ingest-time only; this pass does not introduce historical re-ingest recovery workflows for stale traffic.
