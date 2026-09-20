# External-model operational feasibility

This offline gate answers only whether the exact external-model invocation's
local execution prerequisites are structurally usable at a bound sequence and
policy epoch. Authorization is not operational feasibility: definition !=
grant, grant != admission, and admission != execution. A positive decision is
non-authoritative and can only narrow the existing grant-policy path.

## Bound observations

The digest-sealed decision binds the frozen capability definition, principal,
effect, service, endpoint, model, subject, request and configured-service
digests, their combined admission digest, sequence, policy epoch, a concrete
`RuntimePosture` observation, and sealed transport, request-material, and
credential-path structural readiness declarations. Missing, malformed, stale,
substituted, unknown, unavailable, or governor-blocked evidence fails closed.
No observation establishes remote reachability or authentication success.

Evaluation performs no DNS, socket, TLS, HTTP, provider-health, credential, or
request-material read. Credential readiness says only that the governed path is
structurally configured; credential reference != credential material,
credential material != authorization, and authorization != authentication
success. Material readiness never replaces resolution-time digest checks.

## Current state

Implemented layers are the registered authority definition, runtime grants and
admissions, exact configuration custody, governed credential resolution,
request/response material custody, this deterministic feasibility gate, the
null transport, and durable receipts. `policy_available` remains a separate
policy-system condition.

Production remains infeasible: `NullExternalModelTransport` and
`UnavailableRequestMaterialSource` explicitly declare unavailability. Still
absent are an exact-endpoint HTTPS transport, provider authentication/framing,
live invocation, remote-reachability guarantees, cognition response-trust
policy, and automatic cognition consumption. Response material remains
`untrusted_external_data`.
