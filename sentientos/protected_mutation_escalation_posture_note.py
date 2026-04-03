"""Escalation posture note for covered protected-mutation corridor trust signals.

Escalation posture is a deterministic response-classification layer derived from
existing trust posture evidence for the currently covered corridor only:
- genesisforge_lineage_proposal_adoption
- immutable_manifest_identity_writes
- quarantine_clear_privileged_operator_action
- codexhealer_repair_regenesis_linkage

It does not add remediation and does not replace admission, provenance, fail-closed
write boundaries, forward/strict enforcement, or non-bypass proof checks.

Mapping from trust posture to escalation posture:
- trusted -> none
- not_applicable -> none
- legacy_only -> observe
- forward_risk_present -> forward_block
- strict_failure_present -> strict_block
- evidence_incomplete -> verification_attention

Interpretation:
- observe: legacy-only degradation is visible for operator awareness, not treated as
  fresh blocking risk.
- forward_block: forward-enforcement relevant risk that warrants blocking attention.
- strict_block: strict-mode failure posture requiring highest review posture.
- verification_attention: evidence is incomplete and requires verification attention.
"""

ESCALATION_POSTURE_NOTE = __doc__
