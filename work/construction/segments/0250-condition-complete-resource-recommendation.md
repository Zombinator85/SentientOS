# Sequence 250 - Condition-complete resource recommendations

Resource-backed task-family retrieval now preserves independent `history_present`, `history_withheld`, and `history_restored` outcomes. Each row retains its task/run parent binding, condition-specific inference receipt identity, score digest and evaluator, event time, and independently joined resource receipts. Missing, cross-condition, ambiguous, and unqualified resource evidence remains explicitly unknown; a score cannot qualify an unrelated receipt.

The canonical history input binder can carry a bounded resource-aware recommendation. Its fixed evaluator requires the full correctness criterion from the frozen task descriptor, then ranks eligible conditions by independently scored correct probes and measured `call_units_consumed`. A higher measured cost wins when it is the only condition satisfying quality; equal-quality choices prefer lower measured call units; negative transfer and incomparable evidence remain possible. The recommendation retains the selected inference, score, and resource receipt identities and does not grant authority.

Prompt compaction preserves condition scores, event times, source bindings, measured receipt values, uncertainty, and recommendation identity. The history/epistemic binder now tries smaller history projections before omitting semantic epistemic packets. The adverse-family progression test caught and verified this budget behavior.

Validation: all 92 resident developmental cognition tests passed. The focused family-retrieval and adverse-transfer tests plus resource-lineage, developmental-writeback, and history-intervention suites passed (41 total). Changed Python sources compiled and `git diff --check` passed.

Limitations: the controlled recommendation fixtures use deterministic task scoring and fixture resource rows. They show source integration and bounded decision behavior, not genuine model improvement or production resource performance. Durable retrieval of an actually ledger-backed cross-condition recommendation across a new process remains open.
