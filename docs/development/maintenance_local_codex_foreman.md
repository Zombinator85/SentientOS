# Maintenance local-Codex foreman

Marker: `d1c45cb`.

The local-Codex foreman is an external maintenance component, not part of the SentientOS runtime loop. It gives a lease-bound implementation session one real bounded tool: an explicitly configured local Codex CLI process running in one detached Git worktree. It does not select candidates, grant authority, validate, commit, publish, merge, retry, continue automatically, adopt runtime capabilities, or inspect credentials.

## Authority requirements

The driver kind is `local_codex` and it requires all six explicit effect authority classes in the operator grant, immutable lease, implementation request, and lease action decision:

- `implementation_process_execute`
- `implementation_instruction_disclosure`
- `remote_model_invocation`
- `repository_state_read`
- `repository_workspace_provision`
- `repository_workspace_modify`

`implementation_agent_session` alone is insufficient. Commit, branch publication, remote publication, pull-request mutation, unrelated host actuation, runtime adoption, and unrestricted secret access remain denied.

## Configuration and probing

The closed configuration schema is `sentientos.maintenance_local_codex_foreman_config:v1`. It binds repository identity and roots, external workspace/state roots, configured Codex and Git executables, optional executable digests, Codex home, sandbox posture, model/profile settings when configured, environment-name allowlists, time/output ceilings, recovery limits, output schema digest, and constraints. Unknown fields affecting executable identity, environment, workspace, permissions, model selection, time, or custody fail closed.

The capability-probe schema is `sentientos.maintenance_local_codex_cli_probe:v1`. The foreman probes the configured executable with bounded argv calls for `--version`, `exec --help`, and `exec resume --help`; records version/help digests and executable identity; proves JSONL, stdin prompt, explicit cwd, workspace-write sandboxing, final message/schema output, session/thread identity, and explicit resume support; and rejects unsafe or obsolete posture such as `--full-auto`, `--dangerously-bypass-approvals-and-sandbox`, `--yolo`, `danger-full-access`, skipped repository checks, ignored rules, arbitrary images, arbitrary MCP configuration, or extra command tokens.

## Authentication and environment

Authentication is loaded only from the explicit external `CODEX_HOME`. The foreman does not run `codex login`, browser authentication, device-code authentication, credential creation, token refresh, or interactive prompts. It may verify that the configured authentication root exists and is outside repository/worktree/state custody, but it does not read, hash, copy, serialize, or print credential bytes. Authentication failure is classified as `foreman_authentication_unavailable`.

The child environment is sanitized. Only documented names such as `PATH`, `HOME`, `CODEX_HOME`, `TMPDIR`, certificate/locale names, and explicit allowlisted names are passed. Environment values are not persisted; only allowed names, required-name presence, and a digest of the name set are recorded.

## Worktree custody and instruction disclosure

The worktree descriptor schema is `sentientos.maintenance_implementation_worktree:v1`. The foreman creates or exactly reuses one deterministic detached worktree beneath the external workspace root with `git worktree add --detach <worktree> <base_sha>`, using argv and `shell=False`. The worktree is outside the canonical checkout and state root, remains at the exact base SHA, creates no branch or commit, and is retained for validation or recovery.

The instruction envelope schema is `sentientos.maintenance_local_codex_instruction_envelope:v1`. It binds task, lease, candidate, admitted scope, attempt/session, retry/recovery ordinal, base SHA, admitted paths, validation expectations, budgets, immutable constraints, and the digest-bound external instruction artifact. The fixed guard header says to work only inside the worktree, modify only admitted paths, never commit/push/create PRs, never alter authority or access credentials, avoid hosted-check waits, and stop when implemented or blocked. The opaque instruction bytes are appended without reinterpretation.

## Invocation, JSONL, and process supervision

The invocation schema is `sentientos.maintenance_local_codex_invocation:v1`. The foreman persists immutable invocation custody before launch, including configuration/probe/worktree/envelope/schema digests, sanitized argv, environment-name-set digest, transcript/stderr/final-message paths, timeout, heartbeat interval, and recovery ordinal.

Production invocation uses `codex exec` with argv, never a command interpreter; `shell=False`; a dedicated process group/session; the exact worktree as cwd; instruction bytes through stdin; JSONL stdout; private bounded stderr; and process-tree termination on timeout, cancellation, exception, or controller shutdown.

The JSONL observation schema is `sentientos.maintenance_local_codex_jsonl_observations:v1`. The parser bounds each line and transcript total, rejects invalid UTF-8 and malformed JSON, preserves unknown event types without treating them as success, captures exactly one thread/session ID, rejects conflicting thread IDs, records command/message/usage summaries, and separates terminal process state from advisory agent text.

## Results, recovery, and cancellation

Terminal classifications are closed: `implementation_ready_for_validation`, `implementation_blocked`, `implementation_failed`, `implementation_timed_out`, `implementation_cancelled`, `implementation_interrupted`, `implementation_scope_violated`, `implementation_budget_exceeded`, `implementation_no_change`, `foreman_authentication_unavailable`, `foreman_cli_incompatible`, `foreman_output_invalid`, `foreman_workspace_invalid`, `foreman_process_conflict`, and `foreman_recovery_unavailable`.

A successful result means only `implementation_ready_for_validation`: the Codex process exited successfully, one completed turn was observed, a valid structured final message exists, the worktree has a bounded non-empty change, changed paths and measured budgets remain within the lease, and private evidence was recorded. Validation remains pending. No test pass, validation pass, commit readiness, commit, or publication is implied.

The change-manifest schema is `sentientos.maintenance_implementation_change_manifest:v1`. It independently inspects actual worktree status, changed paths, tracked/untracked classification, file type, content digest where bounded, additions/deletions, file and line counts, out-of-scope/forbidden paths, and budget findings. A private patch is preserved for later validation and recovery.

Recovery resumes only the same captured Codex thread when the prior process is terminal, the lease/attempt remain active, the worktree identity and HEAD are unchanged, no terminal implementation success exists, recovery count permits it, and the deadline is valid. Cancellation verifies task/session identity and process-group evidence before signalling, terminates the process tree, records one terminal cancellation result, and is idempotent.

## Test harness and acceptance boundary

Repository acceptance uses a process-real fake Codex CLI only. The fake CLI emulates version/help/new exec/resume exec, JSONL progress, final messages, bounded mutation, authentication failure, malformed streams, timeouts, cancellation, scope and budget violations, interruption after thread capture, and same-thread resume. No real Codex invocation or remote model call was performed during repository acceptance.

This task creates real bounded implementation capability, but it does not create a fully closed maintenance loop. The next stage remains the proportionate validation and corrective continuation controller. The operator must separately install and authenticate the Codex CLI before live use.
