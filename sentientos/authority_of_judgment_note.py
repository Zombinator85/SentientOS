"""Bounded jurisprudence note for explicit authority-of-judgment rules.

An authority-of-judgment rule is a class-local reconciliation contract that
states which decision surface is authoritative when advisory signals disagree.

Implemented explicit classes in this repository:
- federated_control_admission
- maintenance_admission_proof_budget
- merge_train_mergeability_protected_mutation

Consumption (observability-only):
- ``scripts.emit_contract_status`` now reads ``sentientos.bounded_jurisprudence``
  via ``sentientos.jurisprudence_consumption`` and emits an
  ``authority_of_judgment_jurisprudence`` domain row in ``contract_status``.
- ``sentientos.observatory.fleet_health`` consumes that existing contract-status
  row as a bounded ``jurisprudence_interpretive_signal`` for release-readiness
  interpretation only (constitutional legibility support).
- The consumer reports emitted-vs-consumed mapping for explicit classes and
  unresolved-class visibility; it does not adjudicate, mutate admission, or
  introduce cross-class precedence.
- A missing/gapped jurisprudence mapping can degrade interpretation/readiness
  posture, but cannot grant adjudication authority or override kernel/governor
  merge/runtime authorities.

This remains a bounded implemented jurisprudence surface, not a universal
precedence engine. Authority-of-judgment stays class-local and non-universal.
"""
