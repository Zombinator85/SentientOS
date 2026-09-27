# Initial POSIX resident commissioning runtime

## Maturity boundaries

**Authority contract registered** — PR #2213 registered the exact capability,
principal, thirteen effects, required goal language, and forbidden successor scope.
That registration was eligibility metadata, not runtime approval.

**Runtime initial commissioner implemented** — the controller and operator CLI now
provide a read-only host doctor, deterministic manifest and intent, external
approval verification, narrow control-plane admission, immutable commissioning
custody, one canonical launch contract, reconstruction, and tamper verification.

**Generation zero actually commissioned** — not established by implementation or
synthetic tests. It is true only when a production manifest, qualifying external
approval, ALLOW decision, and completed external custody receipt exist.

**First resident actually launched** — not established in this repository task.
The production path permits only the exact Python realpath with `-m sentientosd`,
the exact repository working directory, and bounded sealed environment. Test
launch adapters and synthetic approval are explicitly rejected by production.

**Successor adoption** — remains a separate later boundary owned by maintenance
authority continuity, successor-generation adoption, and resident-runtime
adoption. Initial commissioning neither derives generation one nor invokes the
resident self-exec transition.

## Runtime sequence

The CLI exposes `doctor`, `prepare-intent`, `show-approval-bindings`, `commission`,
`status`, and `verify`. Only `commission` can mutate commissioning custody or
launch. The required order is read-only inspection, deterministic intent,
independently supplied approval, exact `INITIAL_RESIDENT_COMMISSIONING`
control-plane admission, incomplete-marked construction, native-schema
verification, bounded initial launch, launch provenance, immutable receipt, and
terminal marker. A denial occurs before custody creation. A partial transaction
retains its incomplete marker and cannot reconstruct as commissioned.

The manifest explicitly binds repository identity/root/commit/tree/ref, Python
and daemon entrypoint, external custody, activation profile and bundle, initial
wake adoption, operator reference, lineage, STOP marker, environment, and finite
lifecycle bounds. There is no latest-file discovery.

## Authority and nonclaims

A completed receipt grants no future maintenance or adoption authority. The
implementation performs no generation-one derivation, successor selection,
resident replacement, Git mutation/publication, provider/network operation,
automatic rollback, or post-adoption campaign. It makes no claim of recursive
self-improvement, autonomous software authority, consciousness, sentience,
personhood, or phenomenal continuity.

The strongest implementation-only claim is: SentientOS implements a bounded,
externally operator-approved initial POSIX resident commissioning controller that
can construct and verify generation-zero continuity/adoption custody and an exact
initial `sentientosd` launch contract under separate control-plane admission,
while leaving all successor selection and future resident adoption to their
existing authority boundaries.
