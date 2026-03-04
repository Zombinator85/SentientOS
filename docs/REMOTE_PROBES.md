# Remote Probes

Remote probes are read-only trust checks over exported artifacts from another node.

## Export a bundle

```bash
python scripts/remote_bundle_export.py --out /tmp/probe_export --last-n 25
```

The bundle layout is deterministic:

- `remote_bundle/manifest.json`
- `remote_bundle/artifacts/*.json`
- `remote_bundle/signatures/attestation_snapshots/*`
- `remote_bundle/signatures/operator_reports/*`

## Run a probe

```bash
python scripts/remote_probe.py --bundle /tmp/probe_export/remote_bundle --last-n 25 --json --write
```

Exit codes:

- `0` verification succeeded and no critical divergence.
- `1` warning (non-critical divergence or missing optional stream).
- `2` failure (signature/hash verification failure or critical divergence).
- `3` missing critical artifacts.

## Signing

Probe reports can be signed through operator report signing when:

- `SENTIENTOS_REMOTE_PROBE_SIGNING=hmac-test` or `ssh`

Signing is off by default.

## Forensics

Remote probe flow never writes to or mutates remote nodes. It only reads exported artifacts and emits local report artifacts.
