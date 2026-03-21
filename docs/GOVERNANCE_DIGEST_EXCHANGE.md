# Governance Digest + Pulse Protocol Exchange

Peers exchange governance digests and explicit pulse protocol claims before
high-impact control admission.

Governance digest compatibility states:
- `exact_match`
- `compatible_family`
- `patch_drift`
- `incompatible`

Pulse protocol compatibility states:
- `exact_protocol_match`
- `compatible_family`
- `patch_compatible`
- `deprecated_but_accepted`
- `incompatible_protocol`

Replay-window harmonization states:
- `peer_within_compatible_replay_horizon`
- `peer_outside_accepted_replay_horizon`
- `peer_too_stale_for_replay_horizon`
- `incompatible_replay_policy`

Equivocation posture states:
- `no_equivocation_evidence`
- `weak_equivocation_signal`
- `confirmed_equivocation`
- `protocol_claim_conflict`
- `replay_claim_conflict`

Key artifacts:
- `glow/federation/governance_digest_mismatch_report.json`
- `glow/federation/pulse_protocol_posture.json`
- `glow/federation/equivocation_summary.json`
- `glow/federation/equivocation_evidence.jsonl`
