# Sovereign model-mirror publication

The dockworker in `sentientos.model_mirror_publication` consumes the previously
admitted `sentientos.model_mirror.publish` definition. It does not alter that
taxonomy: only the `deterministic_publication_controller` principal and the four
registered effects are accepted. A request, curator package, artifact, provider
configuration, or credential possession is not a grant. The supplied grant/lease
must cross-bind the request's capability, principal, effects, correlation, grant,
and lease identities.

Before an adapter is called, the controller verifies the curator package's byte
digest, its exact request bindings, the sole HTTPS host `models.sentientos.org`,
the hash-bearing object name, the source's containment below an operator-selected
artifact root, non-symlink regular-file status, exact size, GGUF magic, and a
streamed SHA-256. Git LFS pointers are rejected.

## Provider and secret boundary

`PublicationProvider` is the deliberately narrow adapter contract: inspect one
canonical object, create it once from an iterable of chunks, and independently
stream it back. Provider selection and credentials are not request fields.
Credentials remain operator-supplied internal adapter state and are never logged
or serialized. `DeterministicFakeProvider` is test-only; it is not a production
transport. No backing provider for `models.sentientos.org` is identified or
configured in this repository, so live operation truthfully stops with
`provider_configuration_unavailable` rather than substituting another service.

Create-only behavior has three outcomes. An absent object may be created under a
valid grant. An existing object is never written and becomes
`already_present_verified` only after full streamed SHA-256 and size verification.
A differing object is a hard custody failure and is never repaired or overwritten.
Interrupted or failed uploads cannot emit a receipt.

## Receipt and catalog gate

The atomic, no-clobber `sentientos.model_mirror_publication_receipt:v1` separates
upload attempted/completed, object exists/verified, transfer byte counts, provider
identity, full remote verification, and final status. It contains no credentials.
Only a digest-valid receipt with exact model, digest, URL, and complete streamed
remote SHA-256 makes the frozen catalog **eligible**. The gate neither deploys the
catalog nor grants catalog deployment authority; that separate authority remains
required.

Focused validation:

```text
python -m scripts.run_tests -q tests/test_model_mirror_capability_admission.py tests/test_model_mirror_publication.py
python -m mypy sentientos/model_mirror_publication.py
```
