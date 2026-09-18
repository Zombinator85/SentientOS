# Runtime admission evidence lifecycle

`RuntimeAdmissionAuthority` is the independent deterministic control-plane owner
for non-effectful permission evidence. It accepts only definitions supplied by the
authoritative registered catalog, requires the definition's exact subsystem,
principal kind, complete effect set, and affirmative preconditions, and binds the
result to the definition digest and version. It cannot invoke an actuator.

The lifecycle is: registered definition → bounded issuance → independent
verification/consumption → separate effect execution → separate execution
evidence. Definition is not admission; admission is not execution; execution is
not success. A consumer receives `RuntimeAdmissionVerifier` only and cannot issue
its own permission.

The atomic, digest-sealed ledger persists admissions and later revocations. A
monotonic sequence bounds validity. Verification reloads and validates the ledger,
then rejects changed definitions or exact bindings, expiry, a later revocation, or
a later admission naming the evidence as its predecessor. Thus admission → expiry,
revocation, or supersession → invalid admission, including after restart.

The external-model custody controller can consume this generic evidence through
its verifier boundary using an inert test definition. This does not register
`external_model_inference`, enable its null transport, resolve credentials, contact
a provider, or grant runtime model authority.

