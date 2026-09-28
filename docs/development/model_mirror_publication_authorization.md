# Model-mirror publication authorization

SentientOS implements an installation-authenticated, bounded authorization bridge for
sovereign model-mirror publication. `ModelMirrorPublicationIntent` is immutable evidence
(`sentientos.model_mirror_publication_intent:v1`), not authority. It binds the exact
curator package, model and artifact bytes, content-addressed object and canonical URL,
target capability/effects, publication correlation, and non-secret provider-config
identity/digest. Grant and lease identifiers cannot enter the intent.

An independently supplied `publication_authorization_approval:v1` binds the exact
intent, operator provenance, registered issuer/effects, both correlations, finite
requested intervals, target authority, and provider-config identity. The runtime request
uses `publication_authorization_request:v1`. After an exact
`LOCAL_AUTHORIZATION_GRANT_ISSUANCE` allow, the issuer creates immutable grant, narrower
lease, and cross-bound receipt v1 records. Maximum grant lifetime is one hour; leases
neither exceed nor renew their grant. Active, digest-valid revocation v1 evidence
disables a grant or lease without rewriting history.

Authorization records use authenticated `InstallationStateHandle` custody at the fixed
`authorization/model-mirror-publication` object, with installation identity, exclusive
locking, no-follow substrate checks, durable create-only records, and exact replay. This
custody is distinct from provider storage and publication-receipt custody.

`authorization_correlation_id` admits issuance. A distinct
`publication_correlation_id` admits publication on the same kernel. Reuse is forbidden;
kernel phase/correlation dedupe must not be evaded with another kernel. Projection
verifies finite intervals, revocation, semantic digests and cross-bindings, exact
intent/target/effects/correlation, and production exclusion of synthetic evidence. It
produces hardened `sentientos.model_mirror_publication_grant:v2`; its request-binding
digest binds intent, grant, lease, issuance receipt, and publication correlation.
`materialize_publication_request`—not a caller—adds issued IDs to the effect request.

`AuthorityClass.MODEL_MIRROR_PUBLICATION` denotes only the exact publication effect;
declaration grants nothing. `publish()` requires its real `ALLOW` before local artifact
or provider access for hardened authority. The receipt binds the admission, intent,
projected authority, authorization records, provider configuration, and effect set.
Canonical-host, GGUF, safe-path, create-only, and full remote-byte verification laws
remain unchanged.

Provider metadata uses `sentientos.model_mirror_publication_provider_config:v1` and an
opaque credential reference, never credential bytes. Reference possession is not
authority. No production provider was selected or implemented; the truthful prerequisite
is `production_publication_provider_unconfigured`.

```text
definition != grant
approval != grant
grant != lease
lease != effect admission
effect admission != successful publication
publication receipt != catalog deployment
```

Tests use synthetic evidence, a local GGUF fixture, one real kernel, and the explicitly
test-only deterministic provider. No production effect is performed.

