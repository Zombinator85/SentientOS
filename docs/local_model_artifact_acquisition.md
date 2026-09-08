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
`--confirm-plan-digest`, an authenticated installation identity, externally
supplied approval JSON, and an exact runtime control-plane admission. Caller
catalogs remain preview-only.

The only network authority is the exact URL validated by the production catalog.
The catalog permits credential-free HTTPS at `models.sentientos.org`, binds the
content-addressed filename, and permits no caller URL or fallback. Redirects are
bounded and remain within the catalog-trusted host policy.

Execution streams bounded chunks through the shared exact-artifact primitive,
checks Content-Length when present, enforces exact byte count and SHA-256, and
publishes private staging atomically into `sha256/<digest>/`. Existing bytes are
accepted only after regular-file, exact-size, streamed-hash, and deterministic
v2 receipt verification. Legacy v1 receipts fail closed and are never upgraded.
A repeat reports `already_present_verified` without
changing canonical receipt identity.

Catalog presence is not acquisition. Selection is not acquisition. Backend
verification is not model acquisition. Acquisition is not GGUF compatibility
proof, loading, commissioning, or inference authority. No runtime installation,
runtime import, backend probe, prompt assembly, provider invocation, model
construction, or inference occurs.

## Production authority contract

The existing `authorization_for(plan, operator_confirmed=...)` helper is a
legacy, caller-constructible authorization shape. It is not accepted by the
production `execute=True` path and remains only for historical inspection.

The only admitted task-authority principal is
`deterministic_model_artifact_acquisition_controller`, for capability
`local_model_artifact_acquisition`. Its exact effects are reads of operator
approval evidence, authoritative deployed-catalog proof, and the exact
acquisition plan; one bounded exact HTTPS artifact stream; one exact
content-addressed escrow write; and one acquisition-receipt write. The narrow
control-plane schema identity is `MODEL_ARTIFACT_ACQUISITION`. Definition
eligibility and that schema declaration grant no capability and perform no
effect.

The hardened controller consumes immutable, externally supplied
approval for one exact transition. The runtime does not produce approval.
Evidence is semantically tamper-evident and externally attributable, but the
repository does not claim cryptographic human authentication or supply a
real-world approval actuator. Evidence must bind operator identity;
approval evidence identity and digest; target principal and capability; the
exact effect set; installation identity; authoritative catalog custody identity
and proof digest; deployment receipt identity and digest; acquisition-plan
digest; model ID; artifact content identity, SHA-256, and size; exact canonical
source URL; exact content-addressed escrow destination identity; correlation
ID; and a bounded validity interval. No approval builder that can manufacture
genuine approval is admitted by this contract.

Immediately before network and filesystem effects, the executor
require both genuine explicit operator approval and exact ControlPlaneKernel
admission, each bound to the currently revalidated authoritative deployed
catalog and exact acquisition plan. A structurally valid plan is not execution
authority; authoritative deployed-catalog proof is not execution authority;
operator approval is not control-plane admission; control-plane admission is
not successful acquisition; and an acquisition receipt is not commissioning
authority. The resulting
`sentientos.local_model_artifact_acquisition_receipt:v2` binds the exact
approval and stable control-plane decision lineage, observed transfer facts,
and explicit no-commissioning/no-activation/no-inference posture. The kernel's
normal lifecycle, runtime-governor, panic/startup mediation, proof-budget,
authority-of-judgment, decision logging, and process-local admission-dedupe
paths apply; acquisition has no bypass. The generic fulfillment-authorization wing remains metadata-only,
pre-fulfillment law that blocks network egress and is not model-download
execution authority.
