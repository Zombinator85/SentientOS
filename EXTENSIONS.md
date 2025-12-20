# Extensions Boundary

Extensions are optional observers layered on top of the SentientOS core. They are:

- **Optional and non-authoritative:** Core must boot, operate, and shut down correctly without any extension installed.
- **Read-only:** Extensions may subscribe to telemetry or pulse outputs but may not alter admission, execution, or planning.
- **Isolated:** Core code must never import from extension packages; dependency edges flow only from extensions → core.
- **Governed:** Operators must treat extension outputs as informational. Any control action still requires admission and audit.

No extension implementations live in this repository. Future adapters must conform to this read-only contract and remain outside of the deterministic core.
