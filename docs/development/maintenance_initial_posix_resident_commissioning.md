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

**First resident actually launched** — the production path is executable, but a
repository integration test is still test evidence rather than evidence of an
operator-host commissioning. The path permits only the exact Python realpath
with `-m sentientosd`, the exact repository working directory, and bounded
sealed environment. Test launch adapters and synthetic approval are explicitly
rejected by production.

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

The former implementation used `subprocess.run(..., timeout=...)` and inspected
provenance only after exit. Because a healthy `sentientosd` is a resident loop,
that ordering guaranteed that the timeout killed the healthy child. The repaired
commissioner launches exactly one detached child, retains its PID, and polls for
bounded startup evidence rather than process exit. It cross-checks generation
zero, repository commit and tree, adoption config, executable, entrypoint, cwd,
argv, bounded environment identity, PID, process-instance identity, and intent.
Only then does it write the receipt and intent/process-bound `COMMISSIONED`
marker; successful return therefore does not require resident exit.

On the exact sealed initial-launch environment only, `sentientosd` captures its
ordinary resident provenance and enters an initial commissioning startup gate
before constructing maintenance owners or running a maintenance tick. The gate
publishes `startup-ready.json`, accepts only the matching terminal receipt and
marker, and times out fail-closed. It is absent from normal startup and from
later N→N+1 `execve` environments. A commissioner crash therefore leaves no
ungated maintenance resident.

The standalone operator CLI requests `RUNTIME`, the phase a fresh real
`ControlPlaneKernel` represents. `INITIAL_RESIDENT_COMMISSIONING` has no runtime
governor delegation: the authoritative admission surface is the phase-aware
kernel's exact authority-class/actor request, following manifest-bound external
approval. No delegated governor approval is claimed.

Production reads the manifest-bound approval path (and rejects a different
resolved path or different bytes), closed schema, external source, non-synthetic
posture, nonblank approval/operator/provenance identities, exact bindings,
valid interval, and digest. The digest is byte-integrity and binding evidence,
not authentication; operator provenance remains externally supplied evidence.
Neither commissioner nor CLI manufactures approval.

Completed custody is historical commissioning truth and reconstructs without
requiring the original PID to remain alive. Current resident liveness is a
separate observation. This controller owns one initial launch only: it does not
restart the child (parent supervision remains separate) and it does not perform
later resident self-`execve` succession.

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

The strongest implementation-only claim is: SentientOS implements an executable
bounded initial POSIX resident commissioning protocol in which a real
long-running generation-zero `sentientosd` process can establish exact startup
provenance while maintenance remains gated, after which independently supplied
operator approval and exact control-plane/custody verification can atomically
complete commissioning and release the resident into normal operation.
