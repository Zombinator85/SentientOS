# SentientOS v1.0.0 Release Notes

## Overview
SentientOS v1.0.0 is the first stable cathedral release focused on autonomy, provenance, and composable governance. The platform now aligns ledgered automation, llama.cpp presence services, and the Lumos safeguard framework into a cohesive production posture. This build graduates the v1.0.0-rc1 rehearsal after consolidating integrity data, provenance records, and roadmap guidance for downstream teams.

## Major Features
- **Unified integrity pipeline** – rehearsal telemetry, ledger snapshots, and manifest data are now bundled into a signed, reproducible manifest to anchor release lineage.
- **GapSeeker amendment generation** – rehearsal insights and automation tooling remain wired into Codex review surfaces, ensuring amendments stay structured and auditable.
- **HungryEyes dual-control risk checks** – updated rehearsal metrics confirm the sentinel model continues to co-monitor with Lumos controls before commit approvals.
- **Autonomy rehearsal** – the autonomy rehearsal harness captures amendment lineage, integrity scores, and amendment metadata for rapid promotion from rehearsal to stable tags.
- **Audit verification** – rehearsal audit summaries, integrity ledgers, and timeline exports are all fingerprinted and folded into the release manifest for rapid validation.

## Security & Safety
- **Immutability manifest** – sacred ledger paths remain protected via the existing immutability manifest; fingerprints are preserved within the signed release bundle.
- **Lumos governance** – privilege gating (Lumos approvals, Sanctuary banners) remains mandatory for amendment execution and is highlighted throughout the documentation updates.
- **Cryptographic sealing** – the release manifest ships with SHA-256 and SHA-512 digests for binaries, documentation, and ledgers, plus a detached Codex signature for verification.

## Testing Summary
- `make ci`
- `python -m scripts.run_tests -q`
- `./scripts/verify_provenance.sh`

## Release Checklist
- [x] VERSION synchronized to 1.0.0 across Python, Rust, C++, and manifest files.
- [x] Release manifest and detached signature stored under `glow/releases/v1.0.0/` with verified digests.
- [x] README badge, CHANGELOG entry, and full release notes published.
- [x] Provenance verification wired into local CI (`make ci`) and tagged GitHub Actions runs.
- [x] Follow-up roadmap (`docs/ROADMAP_v1.1.md`) seeded for the next development iteration.

## Future Work
See [`docs/ROADMAP_v1.1.md`](ROADMAP_v1.1.md) for the v1.1 goals driven by the audit findings and rehearsal telemetry.
