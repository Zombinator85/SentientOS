# Release Provenance & Verification

SentientOS v1.1.0-rc bundles full provenance material for both the Python/Rust codebase and the container images.

## SBOM generation

`make audit` writes CycloneDX SBOMs under `glow/provenance/`:

```bash
make audit
ls sentientos_data/glow/provenance
```

The `python-sbom.json` and `rust-sbom.json` files are produced with the pinned dependency lockfiles. Container builds publish
matching `sentientos-sbom.json` manifests for the CPU and CUDA images.

## Image signing

Images pushed from CI are signed with [cosign](https://github.com/sigstore/cosign). To verify a release:

```bash
cosign verify ghcr.io/sentientos/runtime:1.1.0-rc --key cosign.pub
```

The public key `cosign.pub` is shipped alongside the release notes. Verification prints the digest and the annotations used for
the SBOM location.

## End-to-end checklist

1. Run `make audit && make rehearse --duration 10m --load-profile std && make perf` locally. This refreshes SLO gauges, alert
   snapshots, SBOMs, and secrets reports.
2. Collect the generated artefacts from `sentientos_data/glow/` and attach them to the release bundle.
3. Sign the CPU and CUDA container images with cosign.
4. Publish the signed release notes (see `RELEASE_FINALIZATION_PLAN.md`).

If any alert in `glow/alerts/*.prom` has a `1` value with `severity="critical"`, quarantine the release and investigate before
publishing.
