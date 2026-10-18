# Sequence 382: score only the verified campaign receipt snapshot

A follow-up custody review found a time-of-check/time-of-use gap in `report()`. It verified every completed receipt against the campaign state, then reopened the receipt paths to compute report scores. A valid replacement written after the verification pass could therefore influence the report without matching the state-bound receipt identity.

The regression replaces `trial-1.json` immediately after the verifier returns. Before the fix, the altered but structurally valid outcomes were scored. `_verify_progress()` now returns the exact receipt mappings that it validated, and `report()` computes scores from those mappings without reopening the files. The regression fails before the correction and passes after it.

In the isolated local copy, `python -m scripts.run_tests -q tests/test_production_self_reflection_campaign.py` passed **21/21**. The exact task-acceptance node passed **1/1** with `task_acceptance_ready`; targeted module mypy, Python compilation, and `git diff --check` passed. The copied pre-sequence-382 source and test files matched PR #2371's previously verified Git blob IDs before this increment.

This is an **unpublished local construction increment**, not a verified descendant of PR #2371. The exact PR candidate commit `045dc196c641cecbb3b9cf2313ed05187fd73d4c`, its parent `5da046b5a990a15dbc240053351f74e87393d3a6`, and the candidate tree were absent from the local Git object stores checked. The remaining old object store had only the sequence-379 base commit. A clean exact-candidate clone could not be obtained because this executor could not connect to its configured proxy. Therefore no exact-source metadata-guard result, commit, publication, or merge is claimed; PR #2371 remains a draft.

No model invocation, inference, commissioning, or runtime authority was added. The fix only ensures that a report uses the same immutable-by-value receipt objects whose lineage passed validation. The existing sequence-286 provenance limitation and protected workspaces remain unchanged.
