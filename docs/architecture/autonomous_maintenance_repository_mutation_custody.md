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
handoff is metadata-only and requires an approved proposal, a ledger entry,
ledger reference, or approval reference, and one canonical repository-relative
path representation for both `approved_paths` and `approved_path_digests` keys.
Canonical-equivalent spellings are serialized canonically; canonical duplicate
approved paths or digest keys are contradictions, even when duplicate digest
values match. READY also requires a lowercase SHA-256 approval digest for every
approved file, an `approved_source_revision` that exactly matches the read-only
observed revision from `git rev-parse HEAD`, and exactly one truthful evidence
row per canonical approved path. `is_ready_handoff` independently revalidates
canonical paths, digest mappings, evidence truth, revision equality, empty
reason/risk codes, and false authority/effect flags instead of trusting declared
status alone. Missing approval references, missing digest data, or unknown
source revisions are incomplete; digest mismatches, revision mismatches, unsafe
paths, outside-repository evidence, canonical duplicates, and approved-path /
digest-key set mismatches are contradicted. v1 artifacts remain historical
review metadata and are not sufficient for v2 readiness.

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

## External maintenance landing controller

The legacy daemon repository-mutation handoff remains metadata-only review evidence. It is not effectful, does not stage, commit, branch, push, create pull requests, or adopt runtime capabilities, and review packets do not become authority.

`sentientos/maintenance_commit_publication.py` is a separate external developer-workflow topology. It receives explicit `repository_commit`, `remote_repository_read`, `remote_ref_publish`, and, for PR mode, `pull_request_publish` authority only through the operator grant and immutable maintenance-task lease. It is not a `sentientosd` default authority path and does not leak repository authority into runtime capability adoption.
