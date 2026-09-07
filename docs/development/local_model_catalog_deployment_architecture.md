# Authoritative local-model catalog custody architecture

This document is the canonical state, custody, and recovery contract for the
controller admitted under `sentientos.local_model_catalog.deploy`. Its implementation
is `sentientos/local_model_catalog_deployment.py`; this document does not deploy a catalog, issue a grant or lease, or enable
provider, network, acquisition, commissioning, activation, inference, or consumer
authority. The machine-readable projection is
`sentientos/local_model_catalog_deployment_architecture.py`.

## Installation-scoped custody

Production catalog custody belongs to exactly one concrete SentientOS installation.
It is neither host-global nor operator-profile-scoped. Canonical installation
machinery must supply an authenticated installation identity and its durable state
root; a controller must not infer that root from an environment variable, current
directory, repository checkout, curator escrow, artifact store, or caller-selected
catalog destination. `sentientos.installation_state` now supplies the canonical
machine-state registry, normalized installation identity, authenticated state handle,
descriptor-relative protected-path operations, kernel-backed exclusive locking,
durable immutable creation, and durable atomic regular-file replacement.
`sentientos.model_catalog_custody` binds the fixed catalog paths below to that handle.
These substrate APIs are storage mechanics, not deployment authority.

The platform-independent custody identity is
`sentientos-installation:model-catalog` qualified by the installation identity. The
fixed relative layout beneath the canonical installation-state root is:

```text
model-catalog/
  authoritative-catalog.json
  catalog.lock
  transactions/
  deployment-receipts/
```

The root and every resolved object must remain within the canonical installation
root. Parent traversal and protected-object symlinks are forbidden. Catalogs,
transaction intents/stages, and receipts must be regular files. Relative names are
deterministic; destination override is not an API surface. Secure creation and
least-privilege ownership inherit the installation-state security implementation on
each supported platform rather than assuming POSIX modes. Implementations must use
platform machinery that prevents substitution between path validation and use.

## One concurrency domain per installation

`model-catalog/catalog.lock` names one exclusive deployment-lock domain for this
installation only. While holding it, a future controller must perform recovery
inspection, prior-state observation, CAS comparison, transaction creation, catalog
publication, receipt publication, verification, and finalization. It must re-observe
state after acquiring the lock. Two contenders cannot succeed from one prior digest;
the second observes the new digest and fails as stale. The lock is not repository- or
machine-global and conveys no authority.

## Exact compare-and-swap

Genesis requires the explicit sentinel `ABSENT` and actual absence. Replacement
requires an exact expected previous catalog semantic digest and an independently
read and validated authoritative catalog with that digest. Malformed existing state
is corruption, never absence. The candidate is independently validated with the
canonical catalog validator; its digest is recomputed and must equal the proposed
digest. Expected and observed state must match under the lock, and the candidate
bytes/digest remain fixed through staging and publication. Stale state, an omitted
expectation, and blind overwrite fail closed.

## Complete multi-model publication evidence

Deployment eligibility requires exactly one sovereign publication receipt for every
candidate model and no others. Candidate model IDs, receipt IDs, and receipt model
bindings are duplicate-free. Missing, extra, duplicate, or unrelated evidence fails
closed. Each full receipt is independently checked using the canonical publication
receipt schema and semantic-digest machinery. It must bind the candidate model ID,
artifact SHA-256, artifact byte size, and canonical sovereign URL; prove
`object_verified = true`, `complete_streamed_sha256`, matching remote digest and
size, and a final state of `published_verified` or `already_present_verified`.
Immutable source revision and execution routes are proven by validating the catalog;
they are not attributed to a receipt that does not carry them.

The evidence-set projection uses schema
`sentientos.local_model_catalog_publication_evidence_set:v1` and a model-ID-sorted
array of `{model_id, publication_receipt_id,
publication_receipt_semantic_digest}`. Its semantic digest is canonical JSON SHA-256
and is bound into the deployment request, intent, and receipt.

## Recoverable durable transaction

No two-file atomicity is claimed. Under the installation lock, the controller first
resolves every existing incomplete transaction, validates authority/evidence and the
CAS, then derives semantic transaction and receipt identities. It durably creates an
immutable versioned intent containing the complete authority binding, expected and
observed state, candidate bytes or an exact durable staged-byte identity, evidence
projection, exact final receipt body, and all semantic digests needed for recovery.
It durably stages the validated catalog, atomically replaces the canonical catalog,
durably creates the immutable receipt without clobbering, independently verifies
both, and durably records finalization.

Each file write requires write, flush, and file durability before publication. Each
create, rename/replace, and finalization requires the containing-directory durability
barrier supplied by the supported platform's installation-state machinery. If a
platform cannot provide the required guarantee, deployment fails closed. Intent and
receipt identities cannot be overwritten. Finalized transaction records may be
compacted only by a separately specified evidence-preserving retention procedure;
the deployment controller does not silently delete them.

Recovery classifies exact observed identities:

1. **Prior catalog, no receipt:** not committed; validate the intent and safely abort
   or clean its staged candidate.
2. **Proposed catalog, no receipt:** recoverably committed; reconstruct the exact
   immutable receipt solely from the intent, publish it durably, verify, and finalize.
3. **Proposed catalog, exact receipt:** already committed; verify both and finalize
   idempotently.
4. **Any conflict:** if catalog matches neither prior nor proposal, a conflicting
   receipt occupies the identity, journal identity conflicts, or exact evidence is
   unavailable, preserve all evidence and return manual-recovery-required. Never
   guess, overwrite, or infer success from partial state.

The journal is recovery evidence, not deployment authority. New work is inadmissible
until recovery reaches not-committed, recoverably committed, already finalized, or a
fail-closed manual-recovery state.

## Deployment receipt and authority binding

The receipt schema is `sentientos.local_model_catalog_deployment_receipt:v1`. Its
semantic body binds: transaction ID; controller principal; capability; exact effect
set digest; grant and lease IDs; correlation ID; candidate catalog digest; evidence-
set digest and sorted receipt projection; expected and observed prior state;
genesis/replacement kind; resulting digest; installation and custody identities;
validation outcome; deployment time; and bounded final state. A semantic receipt ID
and `receipt_semantic_digest` use canonical JSON SHA-256 conventions. Receipt
possession proves recorded state only and grants no adjacent authority.

A future controller consumes, but does not issue, an active unexpired grant and
lease. They must cross-bind exact duplicate-free effects, principal, capability,
grant/lease/correlation IDs, installation and custody identities, candidate digest,
and expected prior state. Capability definition, publication authority, publication
success, evidence possession, and transaction intent are not grants.

## Future consumer proof surface

A later, separately reviewed verifier may prove that caller-supplied bytes are the
authoritative catalog for an installation by binding installation and custody
identities, independently observed canonical catalog digest, a semantically valid
successful deployment receipt, its resulting digest, and a finalized or validly
recovered transaction state. This task does not integrate selection, acquisition,
commissioning, activation, chat, or maintenance consumers.

## Explicit non-authority

No provider access. No network access. No credential access. No artifact acquisition.
No commissioning. No activation. No inference. No Git publication. No model-mirror
mutation. No catalog mutation. No runtime or software deployment. No shell authority.
No arbitrary filesystem authority or destination. No mutable alias. No self-grant.
No authority inheritance from publication. The deployment controller and all runtime
consumer enforcement remain deferred. Production grant/lease issuance and the first
real authoritative deployment also remain deferred. The transaction/recovery state
machine only consumes exactly bound authority and no authoritative production catalog
has been deployed by the controller or installation-state substrate.

## Installation-state platform contract

The strong durable-state implementation currently admits POSIX hosts only when
descriptor-relative `open`/`stat`/`unlink`, `O_DIRECTORY`, `O_NOFOLLOW`, `O_CLOEXEC`,
kernel `flock`, file `fsync`, directory `fsync`, and same-directory `os.replace` are
available. Security-sensitive traversal opens every directory component without
following links; files are opened relative to retained parent descriptors and checked
as regular files. Immutable creation uses exclusive no-follow creation, complete
writes, file `fsync`, parent-directory `fsync`, and an independent reopen. Atomic
replacement stages exclusively in the same directory, flushes and checks the stage,
uses descriptor-relative same-directory replacement, flushes the directory, and
independently reopens the result.

Windows/reparse-safe directory traversal and a proven containing-directory durability
barrier are not yet implemented. Windows and any limited POSIX runtime therefore fail
closed with `durable_state_platform_unsupported`; the substrate never reports a
best-effort write as durable success. A failed write, flush, replacement, directory
barrier, type check, protected traversal, or independent verification likewise raises
an installation-state error. A replacement may already be visible if the post-rename
directory barrier fails, but the call still reports failure so later domain recovery
must classify the observed state. This is sufficient plumbing for a later controller's
durable-intent, durable-stage, atomic-publication, durable-receipt, and durable-
finalization sequence; recovery policy intentionally remains outside the substrate.
