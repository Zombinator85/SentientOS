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

### Repository mutation custody v2 sealing

Repository mutation handoffs now use `repository-mutation-handoff.v2`. A ready v2
handoff is metadata-only and requires an approved proposal, an approval/ledger
reference, exact `approved_paths` / `approved_path_digests` set equality, a
lowercase SHA-256 approval digest for every approved file, and an
`approved_source_revision` that exactly matches the read-only observed revision
from `git rev-parse HEAD`. Missing approval references, missing digest data, or
unknown source revisions are incomplete; digest mismatches, revision mismatches,
unsafe paths, outside-repository evidence, and approved-path/digest set
mismatches are contradicted. v1 artifacts remain historical review metadata and
are not sufficient for v2 readiness.

The daemon writes runtime handoff artifacts outside the repository worktree. The
resolved root precedence is: explicit injection,
`SENTIENTOS_REPOSITORY_MUTATION_HANDOFF_ROOT`,
`LOCALAPPDATA/SentientOS/repository_mutation_handoffs` on Windows,
`XDG_STATE_HOME/sentientos/repository_mutation_handoffs`, then
`~/.local/state/sentientos/repository_mutation_handoffs`. Roots equal to or
contained in the repository, including `.git`, are refused. Handoff emission uses
atomic JSON writes and must not create `integration/repository_mutation_handoffs`
or dirty the repository worktree.

No unused Git mutation convenience helper remains. The daemon-facing API is a
repository-mutation handoff reader, not a commit-state API: it does not stage
files, create commits, mutate branches, push, create pull requests, mark
proposals committed, adopt proposals, invoke providers, assemble prompts, or
expand runtime authority. External Codex/operator landing controls, including
finalizer, matrix, supervisor, and PR metadata guard, remain required.
