# Active construction checkpoint

## Current verified state — sequence 602

Sequences 591–593 connect receipt-verified outcomes to canonical planning and bind plan identity to execution. Sequence 594 verifies durable planning evidence reload and rejects foreign-proposition support. Sequences 595–600 establish that rejected, stale, withdrawn, or expired epistemic support cannot drive mutation and remains withdrawn after recovery. Sequence 601 traced the Federation Health producer boundary: hosted execution and App publication work, but health reports read a tracked local snapshot, while the privileged relay reads private unauthenticated HTTP peers and writes a separate file. Sequence 602 prevents recent rows without a valid, normalized peer identity from contributing to a healthy report and records the successful post-merge health execution receipt.

Latest verified main: `6d138c83e65fb168dbff74a5c73b962a7b6c8245`, tree `790eda70740d955a8fef3f545b5e931ae96479e0`
Latest construction segment: `work/construction/segments/0602-federation-health-peer-identity-and-execution-custody.md`
Latest segment SHA-256: `3d6673deaecf3fcedca83e590a527f0fb2213e1110bbca72bf59876c256f7e68`
Sequence: 602 (verified identity admission fix and post-merge execution custody)

The hosted Federation Health workflow ran successfully after source integration on main, event `push`, run 39894532452. Its Administrator preflight passed and its execution receipt is bound to main SHA `d5f16f60cd33e3e757cf943716ee5299dad815ab`. The report remains stale with latest snapshot event 2025-06-05 and explicitly says it is not live telemetry. A fresh scheduled run on post-merge source has not been observed; do not substitute the push-triggered run for scheduled evidence.

Next: investigate why a new scheduled Federation Health run has not appeared, then continue designing a trustworthy authenticated and freshness-bounded input bridge. The current peer URLs are private `.local` HTTP endpoints, the relay output and health input remain separate, and no signed ingestion contract is verified. Preserve the stale status and fail closed until a trusted source, freshness policy, and bounded bridge are proven.
