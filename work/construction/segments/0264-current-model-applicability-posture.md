# Sequence 264 - Compare current and retained model identity

The resident serving adapter now exposes a read-only observation of the already current session identity. It uses the controller's non-invalidating currentness check and does not load, unload, or invoke a model. Cognition compares each retained task-family outcome's protocol-bound source identity with that observed target and preserves the relation and target identity digest in compact history packets.

The resulting postures distinguish same active model identity, different active model identity, and an unbound identity. Even a same-model match remains limited to same task family with task scope unverified. A different or missing identity is never relabeled as applicable evidence.

Validation: six selected task-family projection/progression, protocol drift, and resident-serving tests passed through the isolated pytest environment with repository conftest bypassed; compilation and source whitespace/conflict checks passed. The canonical repository runner still cannot provision dependencies without sandbox network access.

Limits: the posture is evidence for later decisions, not an applicability authorization or cross-model learning claim. No production effects, live forge apply, or authority expansion occurred.