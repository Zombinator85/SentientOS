# Changelog

All notable changes for this release candidate are documented below. The log captures the full Codex stabilization sweep leading up to `v1.0.0-rc1`.

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

