"""Cross-loop coupling note: runtime, doctrine, and evolution/deploy surfaces.

Reverse-coupling matrix (evidence source -> runtime consumer -> causal impact):

1) Runtime-local causal loops
   - Runtime pressure/counters -> RuntimeGovernor budget/arbitration ->
     maintenance admission allow|deny|defer.
   - Audit trust runtime state -> RuntimeGovernor audit_trust posture ->
     federated/amendment/control-plane restrictions.

2) Runtime -> evolution causal bridges
   - RuntimeGovernor rollup reason
     ``runtime_feedback_degraded_maintenance`` ->
     ``scripts.emit_stability_doctrine`` -> ``runtime_integrity_ok=False`` ->
     ``ForgeMergeTrain`` doctrine gate hold.
   - Runtime audit degradation + quarantine pressure -> forge integrity pressure
     / risk budget clamps -> publish/automerge throttles.

3) Evolution/deploy -> runtime causal bridges
   - Merge-train doctrine/deploy failure state
     (``glow/forge/merge_train.json`` held|failed with doctrine/check/merge
     integrity errors) -> RuntimeGovernor runtime_feedback posture synthesis ->
     maintenance-phase ``control_plane_task`` / ``amendment_apply`` denials via
     ``runtime_feedback_degraded_maintenance``.

4) Descriptive-only layers (still non-causal for runtime admission)
   - Fleet health release-readiness summaries.
   - Contract/status observatory aggregates not consumed by RuntimeGovernor.
   - Constitution digest and corridor dashboards that report posture only.

Disagreement map (compact):
- Runtime-causal surfaces: RuntimeGovernor pressure/budget, audit_trust posture.
- Evolution-causal surfaces: merge_train held/failed integrity reasons,
  stability_doctrine audit/runtime_integrity gate.
- Descriptive-only surfaces: contract_status rollups, fleet health summaries,
  corridor dashboards.
- Material split-brain classes:
  1) runtime nominal vs merge-train held integrity failure.
  2) runtime degraded vs doctrine healthy (stale governor/degraded count race).
  3) protected-corridor trust posture trusted locally while body-scale doctrine
     remains degraded.
  4) rollback/deploy warning while maintenance admission remains open.

Reconciled disagreement paths:
- Reconciliation point: RuntimeGovernor evolution feedback ingestion
  (``_load_evolution_feedback_signal``).
- Mechanical rule: merge-train *latest entry* is authoritative for runtime
  admission; stale historical held/failed integrity entries no longer poison
  maintenance admission after a newer nominal entry is present.
- Machine-readable observability: runtime_feedback posture details include
  ``surface_disagreement`` and ``reconciliation`` payload with state/rule.
- Reconciliation point: ForgeMergeTrain mergeability gate
  (``_audit_integrity_gate``).
- Mechanical rule: when protected corridor relevance intersects covered
  protected-mutation surfaces and status is ``strict_violation_present``, that
  strict corridor surface is authoritative for merge/deploy readiness hold;
  body-scale doctrine/contract status remain visible as advisory surfaces in the
  disagreement payload.
- Machine-readable observability: merge-train gate/docket payload emits
  ``authority_of_judgment`` with authoritative/advisory surfaces,
  disagreement/reconciliation state, and authoritative result.

Still-unreconciled split-brain risks:
- Contract status and broader doctrine rollups remain descriptive-only for
  RuntimeGovernor admission.
- Non-strict corridor outcomes (legacy-only, not_applicable, forward-clean) are
  still advisory for mergeability unless body-scale doctrine gates fail.
- Updater/deploy runtime admission classes outside merge-train mergeability are
  not reconciled in this pass.
"""
