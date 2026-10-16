# Sequence 229 - Exact source recovery fallback

The construction path now has a bounded, reproducible GitHub Git Data recovery procedure. It preserves the original checkout, starts from a clean local clone of a verified remote ancestor, hydrates only compare-reported changed blobs, verifies each blob and mode, and requires the complete local root tree to match the remote target before development. Synthetic local commit identity remains separate from upstream custody.

The procedure was exercised for Reconciliation XVI: 136 changed paths were hydrated from GitHub, all blob identities and modes matched, and the reconstructed root tree equaled 0ea8c9e8b385ad05cdc81e8057e811fe4354bef0. The source checkout at sequence 228 was then used for focused tests and subsequent construction. Native Git and pip bootstrap transport remain unavailable in this environment.

Next: continue source work from the recovered seq228 tree; inspect resource-history decision paths, then move to another actionable owner boundary.
