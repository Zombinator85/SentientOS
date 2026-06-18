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
  - Work-item lifecycle attestation review surfaces must keep their proof chain aligned: attestation index builder/verifier lanes, review digest builder/verifier lanes, and review digest index builder/verifier lanes stay registered in `scripts/run_work_item_review_packet_matrix.py` as required matrix lanes whenever their docs or tests are changed.
  - The focused proof for the current review digest consistency surface is `python -m scripts.run_tests -q tests/test_work_item_lifecycle_attestation_review_digest.py tests/test_work_item_lifecycle_attestation_review_digest_index_verifier.py`; use the full work-item matrix when lane membership or matrix behavior changes.
- targeted mypy scope includes new module/CLI (if applicable)
- docs link/index coverage exists (if applicable)
- no runtime authority is widened accidentally

Required posture: required validation lane failures are task-owned until proven otherwise.


## Codex Landing Supervisor
Run `python scripts/codex_landing_supervisor.py evaluate --title "..." --intended-commit-title "..." --matrix-json-path /tmp/work_item_review_packet_matrix.json --summary` after matrix and PR gate; do not finalize unless decision is `ready_to_commit` or `ready_for_pr_metadata`.
