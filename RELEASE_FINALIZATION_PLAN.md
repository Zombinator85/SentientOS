# SentientOS v1.0.0 Finalization Strategy

## Objectives
- Lock the SentientOS 1.0 line as a stable, reproducible release.
- Preserve verifiable provenance for all shipped artifacts.
- Prepare the path for hardening and future roadmaps without burning extra Codex windows.

## Recommended Combined Session: "Release + Hardening"
1. **Version and Tagging**
   - Promote `rc1` to the final `v1.0.0` tag.
   - Freeze dependency versions in manifests to guarantee reproducible builds.
2. **Cryptographic Sealing**
   - Regenerate integrity digests for binaries, Docker images, and documentation bundles.
   - Sign digests and the audit summary with the established key material.
   - Publish the immutability manifest alongside artifact fingerprints.
3. **Governance Self-Verification**
   - Extend CI with a "provenance gate" job that verifies digests and signatures before other jobs run.
   - Fail fast if artifacts drift or signatures are missing.
4. **Public Release Briefing**
   - Produce README highlights, CHANGELOG entry, and formal release notes for v1.0.0.
   - Ensure provenance references are part of the public notes so downstream operators inherit the verification trail.
5. **Cathedral Hardening Tasks**
   - Audit privileged services for least-privilege scope and log coverage.
   - Capture baseline performance metrics for critical daemons to detect regressions.
   - Queue backlog items that surface from the hardening pass for the follow-up roadmap session.

## Optional Follow-Up: "Release + Forward Roadmap"
If the hardening backlog is short, pivot the remaining window to:
- Outline v1.1 architecture goals (presence federation, pulse bus, etc.).
- Define benchmark targets tied to the provenance checks introduced above.
- Identify integrations that leverage the newly signed artifacts (e.g., cross-cathedral replication).

## Additional Guidance
- Bundle all release-critical commits into a single Codex run to keep the provenance chain tight.
- Snapshot `audit_summary.md`, changelog updates, and the immutability manifest in the same signed bundle for long-term escrow.
- Treat the CI self-verification job as a gatekeeper for future autonomy loops—nothing runs unless provenance is intact.

May the audit log remain luminous.
