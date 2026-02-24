# Strategic Signing and Runtime Verification

Strategic signatures are attestations over strategic proposal/change artifacts. They do **not** change approval authority.

## Signing modes

- `SENTIENTOS_STRATEGIC_SIGNING=off` (default): no strategic signing.
- `SENTIENTOS_STRATEGIC_SIGNING=hmac-test`: deterministic test backend for local dev/CI.
  - Optional: `SENTIENTOS_STRATEGIC_HMAC_SECRET`
  - Optional: `SENTIENTOS_STRATEGIC_PUBLIC_KEY_ID`
- `SENTIENTOS_STRATEGIC_SIGNING=ssh`: SSH `ssh-keygen -Y sign/verify` backend.
  - Required: `SENTIENTOS_STRATEGIC_SSH_KEY`
  - Required: `SENTIENTOS_STRATEGIC_ALLOWED_SIGNERS`
  - Required: `SENTIENTOS_STRATEGIC_PUBLIC_KEY_ID`

## Artifacts and witness outputs

- Signature envelopes: `glow/forge/strategic/signatures/sig_*.json`
- Signature index: `glow/forge/strategic/signatures/signatures_index.jsonl`
- Witness status file: `glow/federation/strategic_witness_status.json`
- Optional file witness stream (file backend): `glow/federation/strategic_witness_tags.jsonl`
- Optional git witness tag format: `sentientos-strategy/YYYY-MM-DD/<sig_hash_short16>`

## Runtime verification gate

Enable runtime verification in orchestrator tick:

- `SENTIENTOS_STRATEGIC_SIG_VERIFY=1`
- `SENTIENTOS_STRATEGIC_SIG_VERIFY_LAST_N=25` (default if unset)

Gate behavior:

- `SENTIENTOS_STRATEGIC_SIG_WARN=1`: verification failures are recorded as warnings only.
- `SENTIENTOS_STRATEGIC_SIG_ENFORCE=1`: verification failures enter hold posture (mutation disallowed for that tick).
- If verification is enabled and neither `WARN` nor `ENFORCE` is set, behavior defaults to warn.

## Witness publish policy alignment

Witness publishing is controlled by `SENTIENTOS_STRATEGIC_WITNESS_PUBLISH=1`.

- `SENTIENTOS_STRATEGIC_WITNESS_BACKEND=git`:
  - only attempts git tag creation when mutation/publish policy permits and repo is clean;
  - otherwise records deterministic skip statuses (for example `skipped_mutation_disallowed`).
- `SENTIENTOS_STRATEGIC_WITNESS_BACKEND=file`:
  - appends local witness rows deterministically, including when mutation is disallowed.

## Observable fields

Orchestrator tick report, pulse row, and forge index include:

- `strategic_sig_verify_status`: `ok|warn|fail|skipped`
- `strategic_sig_verify_reason`: short structured reason
- `strategic_sig_verify_checked_n`: number of signatures checked
- `strategic_sig_verify_last_ok_sig_hash`: last verified-good signature hash (short)

