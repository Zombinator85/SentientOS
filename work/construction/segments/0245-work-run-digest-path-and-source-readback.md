# Sequence 245 - Work-run filenames bind digest and remote source readback

Work-run storage now names artifacts solely from the full canonical plan digest. `persist_work_run` rejects a caller-supplied run ID that does not equal that digest-derived identity, so a constructed run object cannot place its artifact outside the work-run directory. Exact-plan recovery uses the same digest-derived path.

The adversarial test supplies `../outside` as a run ID and verifies persistence rejects it without creating an outside artifact. The full progression-focused test matrix passed (37 passed).

Independent GitHub readback exposed that the first upload of `work_plan.py` had been truncated and that an intermediate tree omitted the seq244 continuation entries. A forward-only correction was published: commit `67ec774cb0f21b48837ad19afe752db6b19761e2`, tree `1cb458e4d17ebd41b6eb038cc064b3d1d34a86fb`. The corrected blob SHA matches the local Git blob; remote blob fetch succeeds as UTF-8, and the branch head matches the correction commit. No force update was used.

The transient commits remain in remote history; the live branch points to the corrected tree. Production, command, and effect authority are unchanged.

Next: continue dependent task progression with fresh-process outcome selection, then resume qualified resource-informed recommendations and epistemic revision.
