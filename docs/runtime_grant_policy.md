# Runtime operator grant policy

The runtime authority ladder is:

1. an operator-approved **authority definition** describes the maximum shape;
2. a separately authenticated, digest-bound **operator runtime grant** narrows that definition;
3. deterministic runtime policy checks current epoch, sequence, revocation, and exact bindings;
4. `RuntimeAdmissionAuthority` issues bounded, grant-bound admission evidence;
5. `RuntimeAdmissionVerifier` verifies that evidence;
6. a separate consumer may attempt an effect; and
7. separate execution receipts describe the attempt and outcome.

Therefore **definition != grant**, **grant != admission**, **admission != execution**, and
**execution != success**. Authority may narrow down this ladder and may never broaden.
Definition-registration approval is not permission to exercise the definition.

Grant approval uses a sealed operator evidence artifact, not a caller boolean. Artifact
validity establishes deterministic provenance binding; deployment remains responsible
for custody of authentic operator-origin evidence. Grant state is atomically persisted,
digest sealed, strictly ordered, and reconstructed on restart. Missing, malformed, stale,
expired, revoked, drifted, duplicate, or corrupt state fails closed. No secret is stored.

Grant revocation prevents future admissions. Admissions already issued remain valid until
their own expiration, admission revocation, or supersession. This matches admission
custody's self-contained lifecycle and is explicit in tests. Admissions carry the
originating grant ID and digest, so provenance remains inspectable without making every
verification depend on mutable grant availability.

`ControlPlaneKernel` is unchanged: it does not currently own this grant decision.
`RuntimeGovernor` is also unchanged: operational feasibility is distinct from operator
authority. A caller can supply only the deterministic policy-availability condition; an
unavailable condition denies rather than grants.

Grant creation/revocation belongs to `RuntimeGrantAuthority`; `RuntimeGrantPolicy` only
reads its ledger and holds the admission issuer privately. Effect consumers receive an
admission verifier, not either authority object. Prompt, model, subject, and request text
cannot manufacture approval evidence or mutate grants. All grant operations are local
serialization and comparison: they perform no effect, network, credential, model, or
host operation. The external-model production transport remains null.
