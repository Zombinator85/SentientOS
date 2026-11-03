# Gaming companion authority receipt contract

This contract covers verification of operator-issued receipts used by the
Windows-edge/WSL-core companion. It does not define an issuer, grant authority,
provision trust anchors, issue generations, or start processes. The platform
installation supplies already trusted Ed25519 issuer public keys to
`SignedCompanionAuthorityVerifier` and an already provisioned receipt
directory to `CompanionAuthorityReceiptStore`.

## Signed envelope

An envelope is a JSON object with exactly these fields:

```json
{
  "schema_version": "sentientos.companion_authority_receipt:v1",
  "receipt_type": "deployment_launch",
  "issuer_id": "operator-authority",
  "decision": "allow",
  "issued_at": "2026-11-03T12:00:00+00:00",
  "expires_at": "2026-11-03T12:05:00+00:00",
  "subject": {},
  "semantic_digest": "sha256:<digest of canonical signed fields>",
  "signature": "<base64 Ed25519 signature>"
}
```

The signed fields are `schema_version`, `receipt_type`, `issuer_id`,
`decision`, `issued_at`, `expires_at`, and `subject`. Canonical bytes use UTF-8
JSON with sorted keys, compact separators, and non-finite numbers rejected.
`semantic_digest` is `sha256:` plus the SHA-256 of those canonical bytes;
`signature` is the base64 Ed25519 signature over those same bytes. Receipts are
accepted only when the issuer key is already pinned, the decision is exactly
`allow`, the signature and digest verify, the subject is an exact match, and
the receipt is current and no longer than the verifier's configured lifetime.

## Subjects and storage

- `bridge_generation`: subject is the source ID, generation ID, key reference,
  record issuer, issue time, and predecessor generation. The generation record
  binds the resulting receipt semantic digest.
- `deployment_launch`: subject is action `launch_pair`, deployment ID,
  installation identity reference, runtime handoff reference, and software
  generation digest.
- `role_launch`: subject is the same deployment binding with action
  `launch_role` and the exact `windows_edge` or `wsl_core` role.
- `process_launch`: subject is action `launch_process`, deployment ID,
  installation identity reference, runtime handoff reference, software
  generation digest, role, exact command digest, and digest of the complete
  source/acknowledgment generation pair. The supervisor derives the deployment
  binding from the same validated manifest used to compose the paired runtime;
  a receipt for another installation or deployment cannot authorize this
  process launch even when its command and generation-pair digest match.

Generation receipts are stored as `receipt-<64 lowercase hex digest>.json`.
Launch receipts are stored as `subject-<64 lowercase hex digest>.json`, where
the filename digest is SHA-256 over canonical JSON containing `receipt_type`
and `subject`. Receipt files are read-only to this package; it has no receipt
issuer or store writer. Signature verification protects against a substituted
or altered file, while OS custody of the issuer public keys remains the
platform installation's responsibility.

The focused tests use ephemeral fixture signing keys. They prove the verifier
and lookup behavior only; those keys are not trust anchors, and no fixture
receipt authorizes a real deployment.
