# Changelog

All notable changes for the SentientOS 1.x line are documented below.

## [1.1.0-beta] - 2026-02-05

### Operator Experience
- Delivered a read-only FastAPI dashboard (`apps/dashboard`) visualising `/admin/status`, `/admin/metrics`, and rehearsal artifacts with sparklines and diff viewers.
- Added bearer-token gating (`SENTIENTOS_DASHBOARD_TOKEN`) to ensure only authorised guardians can access runtime telemetry.

### Chaos & Alerting
- Introduced `scripts/chaos.sh` with targeted drills for oracle drops, critic lag, council splits, and curator bursts.
- Implemented safety budgets for reflexion, oracle, and autonomous goals with new `sos_*_rate_limited_total` counters and status reporting.
- Added Prometheus alert snapshots via `scripts/alerts_snapshot.sh` emitting files under `glow/alerts/*.prom`.

### Documentation & Release
- Authored `docs/DASHBOARD.md` and `docs/CHAOS.md`, and expanded `docs/OPERATIONS.md` with budget clamps and alert runbooks.
- Bumped the toolchain version to `v1.1.0-beta` and recorded signed release metadata in `BETA_NOTES.md`.

## [1.1.0-alpha] - 2026-01-15

### Autonomy Hardening
- Added a comprehensive autonomy runtime (`sentientos.autonomy`) that wires feature flags, deterministic seeding, rate limits,
  and circuit breakers across semantic memory, reflexion, critic, council, oracle, goal curator, and HungryEyes modules.
- Introduced `/admin/status` and `/admin/metrics` endpoints exposing health summaries and Prometheus counters/histograms for the
  hardened services.
- Implemented a sandboxed subprocess runner with CPU and memory limits plus a CLI (`sosctl`) to manage rehearsals, goals,
  council votes, reflexion notes, HungryEyes retrains, and metrics snapshots.

### Provenance & Tooling
- Rehearsals now emit signed `REHEARSAL_REPORT.json` and `INTEGRITY_SUMMARY.json` artefacts alongside a metrics snapshot and
  structured runtime log.
- Added `make rehearse`, `make audit`, and new scripts under `scripts/` to automate dry-run rehearsals, integrity checks, and
  metrics exports.
- Documented operations, metrics, and rehearsal playbooks (`docs/OPERATIONS.md`, `docs/METRICS.md`, `docs/REHEARSAL.md`) and
  updated README badges for the alpha release.

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

