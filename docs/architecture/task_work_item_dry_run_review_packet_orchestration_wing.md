# Task Work Item Dry-Run Review Packet Orchestration Wing

This wing adds metadata-only orchestration for reviewer-facing work-item dry-run packets.

It composes existing governed surfaces only:

1. work-item intake
2. lifecycle handoff planning
3. lifecycle dry-run adapter (dry-run mode only)
4. work-item dry-run closure manifest
5. compact final review packet summary

It does not execute workspace effects, agents, scheduling, issue tracker integration, branch/PR mutation, network/provider/prompt paths, or full lifecycle execution.

Primary surfaces:
- API: `sentientos/work_item_review_packet.py`
- CLI: `scripts/build_work_item_review_packet.py`
- Tests: `tests/test_work_item_review_packet.py`, `tests/test_build_work_item_review_packet_script.py`

Mode support:
- `review_only`
- `review_with_dry_run`
- `review_with_dry_run_closure`

Reviewer proof/capability posture:
- capability `work_item_dry_run_review_packet_orchestration` is implemented as metadata-review/dry-run orchestration only.
- proof commands are listed for reviewer awareness and default to `proof_command_not_run` unless explicitly executed.
