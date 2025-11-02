# Changelog

All notable changes for the SentientOS 1.x line are documented below.

## [1.0.0] - 2025-11-02

### Highlights
- Promoted the `rc1` rehearsal build to a stable release with synchronized version identifiers across Python, Rust, and C++ toolchains.
- Finalized provenance hardening by generating SHA-256/512 fingerprints for critical binaries, ledgers, and governance manifests.
- Added a provenance verification stage to the CI pipeline and tagged-release workflow to guard against drift.

### Documentation & Governance
- Published comprehensive `docs/release_notes_v1.0.0.md` outlining the stability posture, security guarantees, and future roadmap.
- Seeded the `docs/ROADMAP_v1.1.md` plan capturing IntegrityDaemon, HungryEyes, batching, CI, and symbolic cognition goals.
- Updated README badges and public changelog messaging to reflect the stable release milestone.

### Tooling & Automation
- Introduced `scripts/verify_provenance.sh` and Makefile integration to continuously audit release fingerprints.
- Captured signed `glow/releases/v1.0.0/release_manifest_v1.0.0.json` artifacts for reproducible attestation and downstream verification.

## [1.0.0-rc1] - 2025-11-02

### Features
- Embedded llama.cpp server assets directly in the C++ service to support offline delivery and deterministic rebuilds.
- Added the local perception stack (camera, audio, talkback) and expand-mode sandbox runner to extend autonomous operation scenarios.
- Introduced the security guardian pipeline and HungryEyes sentinel training flow to harden real-time monitoring.

### Fixes
- Restored the llama-server asset embedding handlers after regression and resolved repository merge conflicts while preserving the local model registry.
- Rebuilt the SentientOSsecondary workspace to repair CUDA builds and ensure cross-platform parity.

### Refactors
- Refined the llama-server asset embedding pipeline and normalized optional import handling across the codebase as part of Codex stabilization.

### Infrastructure
- Implemented Codex-first CI/CD workflows, refreshed dependency baselines, and added a Codex-ready devcontainer for reproducible development.
- Vendored the secondary tree assets (via Git LFS) and installed missing build prerequisites (such as `xxd`) for deterministic builds.

### Documentation
- Documented SentientOSsecondary CUDA build procedures, the Codex testing environment, and the final audit/inspection run for this release.

