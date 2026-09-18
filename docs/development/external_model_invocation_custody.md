# External-model invocation custody primitives

`sentientos.external_model_custody` is deterministic, offline **data custody**.
It represents exact HTTPS endpoint identities (scheme, host, port, and path
scope), service-to-endpoint membership, opaque service-bound credential
references, a typed but unempowered inference-controller identity, bounded
request/result envelopes, required-effect descriptions, and synthetic chained
receipt evidence. Frozen records and canonical JSON/SHA-256 bindings make
substitution and correlation failures reviewable. Secret-bearing keys are
rejected; no prompt content or secret value is stored.

The authority-aware chain is:

    cognition proposes
      -> deterministic request custody
      -> service / endpoint / credential-reference validation
      -> separately granted runtime authority and bounded admission
      -> FUTURE transport (not implemented here)
      -> response custody
      -> invocation evidence

These primitives never call a provider, network, credential store, capability
registry, `ControlPlaneKernel`, or `RuntimeGovernor`. They preserve all of the
following boundaries:

* service configured != service authorized
* endpoint represented != endpoint admitted
* credential reference known != credential use authorized
* request described != request admitted
* required effect described != effect authorized
* receipt schema exists != effect occurred
* deterministic principal identified != principal empowered

The earlier prepared `external_model_inference` definition predates these exact
schemas and is superseded. The current non-granting definition proposal derives
from the implemented custody, runtime-grant, and runtime-admission machinery in
[`governed_external_model_authority_proposal.md`](governed_external_model_authority_proposal.md).
Live credential resolution and transport remain unavailable; definition
registration would grant neither.
