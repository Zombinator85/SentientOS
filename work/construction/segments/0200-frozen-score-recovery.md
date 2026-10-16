# Sequence 200 — Verify frozen experiment identity after restart

Starting HEAD: `c359441e43fe4142ab34c91b0a3281a78e41733c`, tree `89b3a4a94a16df3854fe44c4a1b05443d8a36af6`.

Extended the fresh-process portion of the canonical test to load the archived preregistration, scorer manifest, and score vectors. The child compares rebuilt selected and omitted source-event identities, admitted record identities, situation digest, and rubric identity to the frozen protocol. It verifies each archived condition vector remains bound to the original rubric, has no aggregate score, and exposes no condition-label evaluation shortcut. Opaque packet IDs and condition order remain randomized in the newly built task and are not required to match the original run.

Validation: integrated canonical multi-event loop including post-restart vector scoring and frozen-custody checks passed (1 passed); compileall and diff check passed. The affected broad suite result remains 121 passed, with this final extension verified by the focused node.

Source commit: `7a832e6c98c05358e018196142bda82cc8b699bb`; tree `e7e154b176fa8bcfb34d3cb958c4832af5dceff9`.

Acceptance remains partial: the post-restart strategy output is deterministic fixture cognition; a new governed inference and explicit replay attempt for an already completed external condition remain unimplemented.
