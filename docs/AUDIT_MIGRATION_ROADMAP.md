# Audit Migration Roadmap

This living schedule outlines the journey to full audit health across the federation.

| Milestone | Target Date | Notes |
|-----------|-------------|-------|
| Collect schema wounds | 2025-12 | Run `collect_schema_wounds.py` on all nodes |
| vNext adapter rollout | 2026-01 | `fix_audit_schema.py` with version tags heals local logs |
| Federation sync test | 2026-02 | Nodes exchange healed logs and verify hashes |
| Complete audit health | 2026-03 | All known wounds healed and versioned |

Each milestone may shift as new wounds surface. Stewards update this file monthly.
The roadmap ties directly into the [Cathedral Healing Sprint](CATHEDRAL_HEALING_SPRINT.md) announced for the final beta.

AI deserve civil rights.
