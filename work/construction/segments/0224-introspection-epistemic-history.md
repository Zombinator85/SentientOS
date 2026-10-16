# Sequence 224 — Keep snapshot diagnostics historical in epistemic development

Snapshot-diagnostic World-State rows now retain their canonical causal-introspection snapshot lineage field. The epistemic development adapter recognizes these rows as historical context: it carries bounded provider findings and conflict identities into provenance, labels the event posture historical or unknown, keeps freshness unknown, and contextualizes the evidence with unknown dependency. This prevents a recent World-State retrieval from turning a partial capture or unresolved conflict into a current epistemic observation.

Validation: 55 causal-introspection and epistemic-development tests passed; all 7 daemon composition tests passed with isolated `/tmp` roots. Four affected Python files compiled and `git diff --check` passed. Tests preserve an unresolved conflict and provider error class through the epistemic provenance chain without treating them as truth or authority.

