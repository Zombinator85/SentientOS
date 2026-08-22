# Local runtime dependency bundle acquisition

This operator-confirmed step consumes a selected `sentientos.local_runtime_dependency_plan:v1`, rebinds every planned artifact to the canonical dependency catalog, and streams the five exact wheels into a dedicated content-addressed escrow. Initial and redirected requests are limited to `https://files.pythonhosted.org`; URLs come only from the catalog.

Artifacts publish independently at `runtime-dependencies/sha256/<sha256>/<filename>`, so a verified prefix survives a later failure and a retry safely cache-hits it. Artifact receipts bind only the canonical artifact identity and custody witness: they deliberately omit environment, plan, bundle, and authorization identity so universal wheels can be reused by another authorized bundle. Those product bindings live in the bundle receipt.

A bundle receipt publishes atomically at `runtime-dependencies/bundles/<bundle_digest>/dependency-bundle-acquisition-receipt.json` only after all five artifacts and receipts verify. Every cache-hit bundle receipt is reconstructed and compared against the current plan, catalog, authorization, ordered artifact manifests and receipt digests, counts, totals, readiness fields, and negative authority fields. Existing entries are never overwritten, and peer winners receive the same full verification.

Receipt semantic digests use sorted-key compact JSON and exclude only `retrieved_at` and `receipt_semantic_digest`. Before networking, free space is checked against the sum of missing artifact sizes.

Cataloged dependency is not acquired dependency; one acquired dependency is not an acquired bundle; an acquired bundle is not an installed runtime; an installed runtime is not an import-verified runtime; and an import-verified runtime is not a commissioned model. This step never resolves, installs, extracts, imports, loads, commissions, or grants runtime execution authority.
