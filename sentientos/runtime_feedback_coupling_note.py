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

Bidirectional closure assessment (this pass):
- Cross-loop coupling is now bidirectional for one narrow bridge:
  runtime feedback can hold merge-train, and merge-train integrity failures can
  now tighten runtime maintenance admission.
- Closure is still asymmetric overall: most doctrine/observatory outputs remain
  descriptive and do not yet alter runtime scheduling or admission.
"""
