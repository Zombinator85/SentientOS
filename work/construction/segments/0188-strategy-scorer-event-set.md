# Sequence 188 — Route event sets through the strategy scorer

Starting evidence HEAD: `0c9560a40a86f24dc7f2494fd738086c0bba8be8`, tree `fc8cca0ee5980e5db916446623c06d830c7ff5ab`.

Connected the versioned multi-event consequence set to the existing `score_strategy_experiment` owner through an explicit `consequence_events` input and situation binding. The legacy single-consequence path remains unchanged; mixed single/multiple inputs fail closed. The event-set report preserves separate event citations and states that source admission, applicability truth, and improvement are not established.

Validation: embodied and transfer-packet suites: 35 passed. Source and test compile; `git diff --check` passes. The source and test blob identities are independently verified in the live tree.

This is a fixture-backed scorer composition. The external subject packet builder still admits only one consequence record; no claim is made that multiple admitted events influenced an external model.

Next: extend the existing operator packet builder to select from multiple verified historical records with deterministic event-level selection, exact omission identities, and condition isolation. Keep applicability declarations explicitly unverified and bind each selected event to its own source record/fact.
