# Codex landing commit/body binding

`codex_landing_commit_body_binding` is a local, metadata-only verification rail. It binds pre-commit workspace bytes to a single implementation commit, matrix artifact digest, finalizer artifacts, metadata-guard proof, exact PR body bytes, and a structurally classified publication observation.

Semantic identity includes repository-relative paths, file modes, content SHA-256 values, symlink target digests, base HEAD, intended commit title, focused-test and targeted-mypy command digests, matrix digest, commit SHA/tree/parent/subject, and exact PR body UTF-8 digest. It excludes timestamps, absolute workspaces, temporary roots, PIDs, output paths, and runtime custody paths.

The canonical local sequence is:

1. pre-commit finalizer emits `workspace_binding`;
2. commit exactly once;
3. PR-metadata finalizer emits `commit_binding` and verifies it against `workspace_binding`;
4. metadata guard verifies the revision and artifact chain;
5. body builder parses JSON artifacts and emits body plus sidecar;
6. body verifier returns `pr_body_binding_ready`;
7. clean-tree and current-HEAD checks pass;
8. `make_pr` submits the exact verified body bytes;
9. the external actuator submits the sealed handoff without gaining repository authority;
10. an independent observer supplies hosted PR state and the exact hosted body bytes;
11. hosted-publication custody verification binds that observation to the reconstructed handoff;
12. merge state, when observed, remains a separate identity from the hosted PR head.

Between steps 6 and 8, `seal-publication-handoff` in
`scripts/verify_codex_landing_evidence_binding.py` emits the deterministic
`sentientos.pr_publication_handoff:v1` artifact and returns only
`pr_publication_handoff_ready`. It derives the title, body SHA-256 and byte length,
intended head/tree and parent/base SHA, validation profile, task-acceptance digests,
and governing finalizer/guard/body-binding digests from the already sealed artifacts.
Repository identity and the intended base reference are the only publication-routing
inputs not established by current local landing evidence; they are included in the
handoff digest and must be supplied identically when verifying it. Contradictions,
stale evidence, changed body bytes, or replacement of an existing output with different
bytes fail closed.

An external actuator claiming to honor this evidence must publish exactly the sealed
repository, base, head, title, and body. Wrapper-generated or normalized prose is a
different payload and cannot claim the body binding. The handoff performs no network
access, creates or updates no pull request, and does not observe hosted state. Hosted
head rewriting or any other actuator transformation remains an external custody break
until separately supplied, trustworthy observation establishes what the host received.

## Hosted publication custody

`seal-hosted-publication-custody` and `verify-hosted-publication-custody` extend the
same landing-evidence CLI with the deterministic
`sentientos.hosted_pr_publication_custody:v1` artifact. The verifier reconstructs
the authorized repository, intended base reference and SHA, intended head commit
and tree, title, exact body identity, validation profile, acceptance identity, and
governing evidence digests from a verified `pr_publication_handoff_ready` artifact.
It does not trust duplicated authority fields in the custody artifact.

The externally supplied observation must identify its provenance as an independent
hosted observation rather than an actuator payload echo. Exact or rewritten-tree
classification additionally requires the exact observed hosted body bytes; a
digest-only report is insufficient. Missing facts remain missing. For a merged PR,
the merge commit SHA and tree must be explicitly observed rather than inferred.

The statuses are machine-distinct: `hosted_publication_custody_verified_exact` is
the only exact success; `hosted_publication_head_rewritten_tree_equivalent_custody_break`
records equal trees with a different hosted head and remains non-exact;
`hosted_publication_mismatch` records material contradiction; and
`hosted_publication_observation_insufficient` records missing or non-independent evidence.

The full custody chain is: local workspace → implementation commit → exact body
binding → publication handoff → external actuator → independently observed hosted
PR state → merge state. The intended implementation commit, hosted PR head commit,
merge commit, and resulting tree are four distinct identities. Equal trees show
content equivalence only; they do not make commit objects equal and cannot satisfy
an exact-head publication contract. The `sentientos.pr_publication_handoff:v1`
semantics are unchanged and never authorize actuator rewriting.

`ready_to_commit` is not a commit. `ready_for_pr_metadata` is not a PR. `pr_metadata_guard_ready` is not a PR. `pr_body_binding_ready` only authorizes submitting exact bytes. A title/body payload echo is not remote publication. Only concrete external remote evidence can advance remote-state classification; this rail performs no remote API calls and grants no branch, push, merge, or PR-creation authority. Sealing custody classifies supplied evidence only; it does not manufacture hosted observation or hosted success.

Finalizer subprocesses use external runtime roots by default (`/tmp/sentientos-codex-finalizer/<binding-id>`) and export `SENTIENTOS_DATA_DIR` plus `SENTIENTOS_RUNTIME_STATE_ROOT` to children. Roots inside the workspace or `.git` fail closed.
