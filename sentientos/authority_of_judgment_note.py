"""Authority-of-judgment map for currently implemented organism-scale decisions.

Scope constraints for this note:
- Current implemented classes only.
- No new governance taxonomy and no widened corridor/control-plane scope.

Decision classes (current code paths):
1) maintenance admission (control_plane_task / amendment_apply):
   - Authoritative: RuntimeGovernor runtime_feedback + audit_trust posture.
   - Advisory: merge-train evolution signal (ingested into runtime_feedback details).
   - Descriptive-only: contract status rollups, fleet health summaries.
   - Reconciliation: explicit for evolution stale failure clearing via
     ``latest_entry_authoritative`` in RuntimeGovernor.

2) repair admission:
   - Authoritative: RuntimeGovernor local safety + pressure + audit_trust posture.
   - Advisory: runtime_feedback degraded signal (tightening only for repair).
   - Descriptive-only: dashboard/observatory rows.
   - Reconciliation: no dedicated multi-surface reconciliation beyond posture ordering.

3) daemon restart admission:
   - Authoritative: RuntimeGovernor restart budget + pressure posture.
   - Advisory: audit_trust degraded (tightened posture, restart may still proceed).
   - Descriptive-only: merge-train/deploy status.
   - Reconciliation: no explicit disagreement reconciler.

4) federated control admission:
   - Authoritative: RuntimeGovernor decision.
   - Advisory: request metadata ``federated_denial_cause``.
   - Descriptive-only: federation context envelope.
   - Reconciliation: explicit in ControlPlaneKernel
     ``runtime_governor_authoritative_for_federated_control`` when runtime allow
     disagrees with metadata denial.

5) merge-train hold / mergeability:
   - Authoritative: ForgeMergeTrain gate stack + active posture policy.
   - Advisory: runtime doctrine emissions consumed by forge gates.
   - Descriptive-only: status snapshots not consumed by gate decisions.
   - Reconciliation: entry-local gate sequencing; no global cross-surface resolver.

6) updater/deploy readiness:
   - Authoritative: forge readiness gates (throughput/quarantine/risk budget).
   - Advisory: runtime and trust posture exports.
   - Descriptive-only: release-readiness summaries.
   - Reconciliation: no explicit cross-surface authoritative map.

7) protected corridor forward-enforcement:
   - Authoritative: protected corridor classifier + explicit corridor proofs.
   - Advisory: adjacent trust posture artifacts.
   - Descriptive-only: doctrine dashboards.
   - Reconciliation: bounded per-corridor checks only; no broad synthesis.

8) strict proof failure handling (implemented delegates):
   - Authoritative: proof budget governor mode for maintenance admission classes
     (`proposal_evaluation`, `proposal_adoption`, `manifest_or_identity_mutation`,
     `spec_amendment`, `privileged_operator_control`).
   - Advisory: runtime governor allow signal.
   - Descriptive-only: proof budget run context payload.
   - Reconciliation: explicit in ControlPlaneKernel
     ``proof_budget_diagnostics_only_authoritative_for_maintenance_admission``
     when runtime allow disagrees with diagnostics-only proof posture.

Operational ambiguity still unresolved (visible, not hidden):
- restart admission: runtime pressure/budget vs adjacent corridor trust/proof
  artifacts has no dedicated reconciliation rule.
- merge/deploy readiness: forge gate stack vs corridor-local trust/proof posture
  is still resolved by local gate ordering, not an explicit authority map.
- forward-enforcement/strict proof handling outside maintenance admission delegates
  remains intentionally unresolved in this pass.
"""
