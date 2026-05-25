# Codex Capability Landing Checklist

When adding or changing a capability ID, verify all adjacent integration surfaces before first finalization:

- capability category is allowed
- authority level is allowed
- deferred/forbidden implications use existing taxonomy
- proof commands are valid
- reviewer proof bundle artifact kind is registered (if applicable)
- proof bundle filename mapping exists (if applicable)
- proof bundle payload exists (if applicable)
- reviewer readiness/index link tests pass (if applicable)
- matrix runner required lane exists (if applicable)
- targeted mypy scope includes new module/CLI (if applicable)
- docs link/index coverage exists (if applicable)
- no runtime authority is widened accidentally

Required posture: required validation lane failures are task-owned until proven otherwise.


## Codex Landing Supervisor
Run `python scripts/codex_landing_supervisor.py evaluate --title "..." --intended-commit-title "..." --matrix-json-path /tmp/work_item_review_packet_matrix.json --summary` after matrix and PR gate; do not finalize unless decision is `ready_to_commit` or `ready_for_pr_metadata`.
