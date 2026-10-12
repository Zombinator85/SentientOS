## 2026-10-12 — repair and exercise the resource observer handoff

- Reacquired branch `codex/construct-sentientos` at `4ecbde42b4ddf23beb2fd7ecdb30b036fa846bc7`, tree `3aa226608c66b192715f1e16284b01ba503f0395`.
- Added an installed-fixture test through the existing provisioning-bundle producer, an actual read-only observer, `RuntimeMaintenanceSurfaces`, and the actual World-State builder. It exposed two deterministic blockers: validated issuer/currentness views were deleted before verification, and a missing optional runtime-observation parent was treated as invalid custody.
- Repaired both narrow defects. Only a truly absent parent (`state_parent_missing`) is now optional absence; unsafe, malformed, and other storage failures still fail closed.
- The fixture passes with exact installation/provisioning/manifest/allocation identity in World-State. The absence of invocation/consumption stays explicit, shared host usage stays unknown, effect claims remain false, and ledger bytes remain unchanged.
- Focused Forge/remediation plus installed-fixture suites: 40 passed; the installed-fixture case also passed individually. Changed Python compilation and `git diff --check` passed. See `work/resource_observation_world_state_acceptance.json`.
- The earlier hosted lifecycle census remains explicitly bound to 4ecbde4 and now records these failures at that historical source revision.
- Production deployment and Windows behavior remain unverified.
