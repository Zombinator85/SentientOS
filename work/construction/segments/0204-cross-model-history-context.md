# Sequence 204 — Freeze multi-record history across model identities

Starting HEAD: `0459b70fa83169d77ab7e2ff64a6ae1c8a4b48b5`; seq203 source tree `2b9a60bfb5987574075c8470e079ccaf116d1483`.

Extended the existing model-replacement A/B owner test to admit two distinct records through ordinary resident writeback on separate ticks. A later current projection is held fixed while predecessor and successor fixture endpoints run the existing frozen causal context. Both endpoints receive the same ordered record IDs and digests; empty-history control calls remain empty. The two durable records are recovered from the read-only completed-admission inventory.

The fixture keeps model identity distinct from source-record and invocation identities. It establishes context composition across endpoints only; it does not establish model succession, weight adaptation, or cognitive improvement.

Validation: targeted cross-model node passed; affected suites passed (121 passed); compileall and diff check passed. Synthetic source and model fixtures only.

Source commit: `28746579f3261be10b6fbecd28de44260913f8ba`; tree `1b67464c9c809bf6fd1da83e6e05480effc9233b`.

Next: compose these multi-event consequences with model-replacement causal context or advance repeated longitudinal correction.
