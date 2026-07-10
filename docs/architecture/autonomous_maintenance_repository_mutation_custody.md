# Autonomous Maintenance Repository Mutation Custody

SentientOS maintenance no longer has autonomous repository mutation authority.
The `sentientosd` maintenance loop may inspect already-approved amendment
metadata and emit a deterministic, metadata-only repository mutation handoff for
operator/Codex review. The handoff is evidence, not authority.

Current posture:

- `sentientosd` may create review handoffs for approved proposals with explicit repository-relative paths.
- `sentientosd` has no authority to stage files, create commits, mutate branches, push, or create pull requests.
- Repository mutation remains an external operator/Codex landing action governed by the landing finalizer and PR metadata guard.
- Handoff readiness does not authorize Git mutation, merge, adoption, runtime authority, provider invocation, prompt assembly, or network access.
- Any future autonomous Git path requires a separate topology and authority decision.

The handoff schema records `repository_mutation_authorized=false`,
`staging_performed=false`, `commit_performed=false`,
`branch_mutation_performed=false`, `push_performed=false`,
`pull_request_created=false`, `network_performed=false`,
`provider_invocation_performed=false`, `prompt_assembly_performed=false`, and
`runtime_authority_expanded=false`.

`updater.py` / `sentientos-updater` remains an explicit operator-invoked legacy
utility, not a default daemon authority path.
