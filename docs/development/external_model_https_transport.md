# Audited exact-endpoint HTTPS transport

`ExactHTTPSExternalModelTransport` is the production-capable actuator for the
already registered `external_model_inference` effect. It is not an authority
source: construction and structural readiness issue neither a runtime grant nor
an admission. Execution remains downstream of the exact grant, policy,
operational-feasibility, admission, configuration, request-material, and (when
configured) credential-custody chain.

## Configuration and migration

The service catalog is version 2. `ExactHTTPSTransportProfile` is stored inside
`ConfiguredExternalModelService`, so its version, `POST` method,
`application/json` media type, and closed authentication mode (`none`, `bearer`,
or `x-api-key`) participate in `configuration_digest`. A framing change thus
invalidates stale request/configuration, feasibility, grant, and admission
bindings. Version-1 catalogs remain loadable as custody records, but are loaded
without a live profile and cannot construct the live transport. Malformed or
credential-inconsistent profiles fail closed; no legacy entry is silently made
live-capable.

## Network boundary

The constructor captures one validated enabled service. Invocation has no URL,
host, port, path, method, or header argument. The one request uses the exact
configured HTTPS host, port, and path, never URL joining, retries, redirects, or
proxy tunnelling. `http.client.HTTPSConnection` does not consult HTTP proxy
environment variables. A default verified TLS context requires certificate and
hostname verification and supplies the configured host for TLS hostname/SNI
handling. Injected contexts must preserve those verification properties.

Literal loopback, private, unspecified, link-local, multicast, and reserved
addresses, plus `localhost` names, are rejected before connection. Other exact
DNS names are not pre-resolved: this avoids a separate policy resolution followed
by an independently resolved connection, but does not claim DNS or routing
integrity beyond the platform's verified TLS hostname authentication. Readiness
does not resolve DNS, open a socket, negotiate TLS, or probe a provider.

## Material, authentication, and bounds

Only verified bytes passed by `GovernedRequestMaterialResolver` are sent, without
reserialization or mutation. The transport performs no prompt lookup. It accepts
only the transient credential view supplied by `GovernedCredentialResolver` and
constructs the single configuration-selected authentication header. Missing,
unexpected, non-ASCII, or CR/LF-bearing credentials fail before networking.
Secrets and request/response bytes are excluded from errors and evidence.

Connections have a finite 15-second timeout, request material remains limited to
1 MiB, and responses remain limited to 4 MiB. Declared oversized responses fail
before body reading; all responses are nevertheless read with a 4 MiB + 1 cap.
There are no retries. A valid HTTP response is `provider_responded`; only 2xx is
`succeeded`. A 3xx is returned as bounded untrusted response material and is
never followed. I/O failure after connection construction is attempted without a
provider response. Actual response bytes and their digest flow through the
existing independent response verification and `untrusted_external_data`
handoff; raw bytes are not persisted.

## Deployment posture

Implemented layers now include exact registered authority identity, grants,
policy, feasibility, admission, service/endpoint/model custody, governed
credential and request/response material, this exact HTTPS actuator, bounded
authentication framing, untrusted-response custody, and durable receipts.

The null transport remains available and is not automatically replaced. There
is no automatic live-transport activation, provider/account reachability or
credential-validity guarantee, provider-specific response interpretation,
response-trust policy, or cognition/memory consumption. The default
`UnavailableRequestMaterialSource` still prevents complete out-of-the-box live
operational feasibility. A deployment must explicitly compose a profiled
service, a legitimate request-material source, the live transport, and the full
exact runtime authority chain.
