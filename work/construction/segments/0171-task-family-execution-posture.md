## 2026-10-13 checkpoint — retain execution posture with task-family experience

- Continued from remotely verified source commit `d890b6772d6bffc13cdc4b9f8dde2ac6847d789b`; the current source commit is `cabb61b31de94c50b5375e2eedee70cd2e099069` (tree `49564edd7381f823a5836c3784147851db637d25`).
- Admitted task-family examples now carry the three condition-specific owner-receipt execution postures into later cognition. Exact receipt digests remain cross-bound to condition receipt identities; simulation, owner-reported backend entry, unresolved status, and independent observation are kept distinct.
- Writeback rejects partial, substituted, or overclaiming execution evidence. Historical records that predate the fields remain available with execution evidence explicitly unavailable. The canonical selected-evidence ceiling increased narrowly from 9,216 to 10,240 bytes after the composed record measured 9,399 bytes.
- Focused tests passed:
  - `test_admitted_family_example_supports_second_heldout_episode_after_restart`
  - `test_interrupted_scored_family_run_recovers_into_later_world_state_without_replay`
- `py_compile` passed for both changed owners and the focused test module; UTF-8 decoding and NUL-byte checks passed. No real-model invocation or production verification was performed.
- Next: inspect and improve source/task relevance selection with bounded deterministic controls, then preserve positive and adverse experience across a further episode. Actual local-model acquisition remains unavailable without a configured artifact and existing serving authority.
