# Sequence 263 - Preserve source model identity in task-family experience

Objective history already froze the active model identity in its experiment protocol, but the durable outcome projection discarded it. The protocol payload now carries the identity digest, and bounded task-family retrieval verifies that digest before exposing the identity to cognition. Compact packets preserve the same identity and digest. If identity is absent or mismatched, the scored historical examples remain available with an explicit unbound posture; the packet also states that target-model applicability is unbound.

This closes source provenance for later applicability decisions without asserting transfer. The current cognition request does not provide a verified target identity to this projection, so cross-model applicability remains unresolved and must not be inferred from a task-family match alone.

Validation: five selected task-family projection, progression, protocol-binding, and model-drift tests passed with the repository test environment and conftest bypassed; Python compilation passed. The repository runner could not provision its editable install because the sandbox has no network access. Whitespace checking was performed with a direct source scan.

Limits: identity lineage is preserved, but no target identity comparison or cross-model transfer is established. No production effects, live forge apply, authority expansion, or new provider access occurred.