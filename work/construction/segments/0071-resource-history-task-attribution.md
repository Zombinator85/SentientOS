# 0071 — Preserve allocation and experiment context in history scope

Status: focused tests passed; unverified for production.

Source review found that resource-backed developmental-history scope already retained principal, invocation, model/provenance, and software posture, but omitted the allocation identity fields other than the digest and discarded the bounded experiment/task context. This made the history summary less intelligible at the strategy/developmental boundary.

The scope now preserves a bounded allocation tuple (allocation ID/digest, principal binding, epoch/resource kind, and policy digest) and a digest-bound summary of experiment condition, protocol, and history-set identities. It labels that context `recorded_experiment_context_not_sponsorship`; no sponsor or authority is inferred. The existing resource-lineage checks still require the attempt, allocation digest, principal, consumption receipts, invocation receipt, model identity, and provenance to reconcile. Unknown software generation is retained as unknown.

`test_embodied_consequence.py` and the restart/resource-lineage integration suite passed 25/25. Changed Python compiled; source bytes were 180,500, UTF-8 decoded, and contained no NUL. Evidence: `work/construction/evidence/0071-resource-history-task-attribution.json` and JUnit `work/construction/evidence/0071-resource-history-task-attribution-junit.xml`.

No authenticated external task sponsor or source-supported software-generation identity was present in this fixture. No actual-model learning, effect, or production claim is made.
