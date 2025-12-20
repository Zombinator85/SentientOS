# Non-Core Futures and External Adapters

SentientOS core remains deterministic, non-expressive, and non-embodied. Installer behavior, admission, and execution never assume VR, gaming, or sensorimotor hardware. Any interface to those domains must live in external adapters that:

- Ingest read-only telemetry (for example, pulse-compatible status feeds).
- Do not call back into admission, execution, or planning.
- Are optional and removable without impacting core guarantees.

Embodiment, gaming, VR, and sensorimotor integrations are therefore **out of scope for core**. They may be explored as non-core extensions that observe pulse or emit audit-only logs, but they are not part of the deterministic runtime or its schemas.
