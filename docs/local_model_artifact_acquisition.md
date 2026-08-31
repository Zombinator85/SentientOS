# Local model artifact acquisition

The production local-model artifact acquisition organ obtains the exact
catalog-selected opaque GGUF bytes. It reconstructs the production catalog,
validates the selection-plan digest, binds the selected model/artifact/route to
the runtime provisioning plan, and requires the canonical verified-backend
receipt for that same provisioning chain.

The implemented chain is read-only hardware observation → deterministic model
and route selection → runtime provisioning → runtime/dependency acquisition →
offline runtime installation → runtime import verification → selected-backend
verification → **model artifact acquisition** → future GGUF compatibility/load
boundary → future commissioning → future inference authorization.

Inspection composes a deterministic
`sentientos.local_model_artifact_acquisition_plan:v1` and performs no network or
acquisition-root mutation. Execution requires `--execute` and the exact
`--confirm-plan-digest`; authorization binds the plan, artifact, route, catalog
URL, and escrow root.

The only network authority is the exact URL validated by the production catalog.
The catalog permits credential-free HTTPS at `models.sentientos.org`, binds the
content-addressed filename, and permits no caller URL or fallback. Redirects are
bounded and remain within the catalog-trusted host policy.

Execution streams bounded chunks through the shared exact-artifact primitive,
checks Content-Length when present, enforces exact byte count and SHA-256, and
publishes private staging atomically into `sha256/<digest>/`. Existing bytes are
accepted only after regular-file, exact-size, streamed-hash, and deterministic
receipt verification. A repeat reports `already_present_verified` without
changing canonical receipt identity.

Catalog presence is not acquisition. Selection is not acquisition. Backend
verification is not model acquisition. Acquisition is not GGUF compatibility
proof, loading, commissioning, or inference authority. No runtime installation,
runtime import, backend probe, prompt assembly, provider invocation, model
construction, or inference occurs.
