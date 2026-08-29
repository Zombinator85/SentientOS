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
9. publication-result classification inspects supplied platform output;
10. independent remote inspection is required before claiming PR or merge verification.

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

`ready_to_commit` is not a commit. `ready_for_pr_metadata` is not a PR. `pr_metadata_guard_ready` is not a PR. `pr_body_binding_ready` only authorizes submitting exact bytes. A title/body payload echo is not remote publication. Only concrete external remote evidence can advance remote-state classification; this rail performs no remote API calls and grants no branch, push, merge, or PR-creation authority.

Finalizer subprocesses use external runtime roots by default (`/tmp/sentientos-codex-finalizer/<binding-id>`) and export `SENTIENTOS_DATA_DIR` plus `SENTIENTOS_RUNTIME_STATE_ROOT` to children. Roots inside the workspace or `.git` fail closed.
