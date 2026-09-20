# Audit Migration Roadmap

This living schedule outlines the journey to full audit health across the federation.

| Milestone | Target Date | Notes |
|-----------|-------------|-------|
| Collect schema integrity issues | 2025-12 | Run `collect_schema_integrity issues.py` on all nodes |
| vNext adapter rollout | 2026-01 | `fix_audit_schema.py` with version tags heals local logs |
| Federation sync test | 2026-02 | Nodes exchange healed logs and verify hashes |
| Complete audit health | 2026-03 | All known integrity issues healed and versioned |

Each milestone may shift as new integrity issues surface. Stewards update this file monthly.
This legacy roadmap is superseded by current audit migration and integrity-repair procedures.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
