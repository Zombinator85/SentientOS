# Codex Finalize Landing

Use `python scripts/codex_finalize_landing.py finalize` as landing authority.

## Phases
- `--phase pre-commit`: permits intended task files (via `--allow-current-tracked-changes` and `--allow-current-task-files` (or explicit `--changed-file` for tightly controlled tasks)) to be dirty, but still requires validation evidence and blocks unknown/generated drift unless cleanup is allowed and succeeds.
- `--phase post-commit` / `--phase pr-metadata`: requires a clean source tree and only returns PR-metadata readiness when all required validation lanes pass.

## Decisions
- `ready_to_commit`: only valid in `pre-commit` phase.
- `ready_for_pr_metadata`: only valid in `post-commit`/`pr-metadata` phase.
- `repair_required_task_caused`, `manual_review_required`, `environment_blocked`, `do_not_finalize`, `finalizer_failed`.
- `stale_evidence_refresh_required` when validation evidence is stale and refresh was not allowed.
- `stale_evidence_refresh_failed` when an allowed bounded refresh fails or times out.
- `generated_artifact_cleanup_incomplete` when cleanup was allowed but generated artifacts remain after the cleanup/refresh decision point.

## Dirty-tree classes
- `intended_task_change`
- `generated_runtime_artifact`
- `versioned_audit_artifact`
- `source_change_not_declared`
- `unknown_dirty_file`
- `clean`

Pre-commit allows `intended_task_change` when declared by `--changed-file`, inferred from tracked git changes with `--allow-current-tracked-changes`, and inferred from safe untracked task files with `--allow-current-task-files`. Post-commit/pr-metadata blocks all source dirty files.

## Why PR metadata is forbidden early
Focused tests, matrix, gate, or supervisor alone are insufficient. PR metadata is forbidden until the post-commit/pr-metadata finalizer returns `ready_for_pr_metadata`.

## Example flows
1. Normal feature landing: run pre-commit finalizer (`ready_to_commit`) -> commit -> run post-commit finalizer (`ready_for_pr_metadata`) -> create/update PR metadata.
2. Validation-only sealing with no changes: run post-commit/pr-metadata finalizer directly; expect `ready_for_pr_metadata` with clean tree.
3. Stabilization with generated artifact cleanup only: allow cleanup flags and stale-evidence refresh flags; one finalizer invocation cleans artifacts, refreshes matrix/gate/supervisor evidence once, and returns the phase-appropriate terminal status when the tree is clean.


## Canonical two-phase command examples
Pre-commit: run finalize with `--phase pre-commit`, `--allow-current-tracked-changes`, `--allow-current-task-files` (or explicit `--changed-file` entries), and require `ready_to_commit` before commit.
Post-commit/pr-metadata: rerun finalize with `--phase pr-metadata` and require `ready_for_pr_metadata` before `make_pr` and final reporting.

When an authoritative exhaustive matrix has already completed against the unchanged
pre-commit workspace, pass its exact output as `--prevalidated-matrix-json PATH` with
`--validation-profile exhaustive`. The finalizer independently reconstructs the current
matrix contract and canonical matrix workspace binding, verifies the completed artifact
and every lane, and fails closed on any mismatch. Exact acceptance records
`matrix_reused` and `exact_prevalidated_matrix_reuse`; it does not run `matrix_summary`
again. This explicit option never falls back to another exhaustive execution when the
supplied artifact is stale, incomplete, crossed, or tampered.

The reuse comparison requires the v2 schema, `matrix_passed`, zero required failures,
the exact command count and lane manifest, all current required lanes passing, a valid
artifact checkpoint digest, the current matrix-contract digest, and an exact canonical
workspace-binding match. That binding covers HEAD, tracked tree, changed and task-owned
untracked file identities, dependency/lock digests, and the Python executable/version.

## No-change validation-only example
If repository source/doc/test files are unchanged, run the pr-metadata phase for validation evidence only and report completion without commit/`make_pr`.

## Anti-patterns
- Commit + `make_pr` after focused tests only.
- Commit + `make_pr` after partial finalizer usage (pre-commit only).
- Deferring post-commit finalizer to a later seal follow-up turn for task-caused changes.
- Treating `unknown_dirty_tree` without exact path-level diagnostics as acceptable proof.
- Rerunning an already exact authoritative matrix instead of using
  `--prevalidated-matrix-json`.
- Running `git push` or `gh pr create` merely to discover whether an external
  publication actuator exists.

## Clean local terminal report and publication boundary

Repository-local landing ends only after pre-commit readiness, the implementation
commit, post-commit readiness, metadata guard readiness, exact PR-body binding, and a
sealed and verified publication handoff. These satisfied contracts are reported as
successful local stages. External publication is a separate observer-scoped capability.

Capability discovery must precede actuation. If no compatible authorized external
publication actuator is exposed to this execution, do not invoke `git push` or
`gh pr create`. Record the existing observer facts `actuator_not_exposed_here`,
`publication_not_performed_by_this_execution`, `hosted_publication_not_observed`, and
remote existence `unknown`. This is a successful local terminal state, not a validation
warning, landing failure, or claim that a hosted PR does not exist. A compatible
authorized actuator that is actually invoked must still report any real failure.

The canonical successful report shape uses successful local-stage markers through
`pr_publication_handoff_ready`, followed by neutral prose (or a successful contract
marker) stating that external publication was correctly not attempted because no
authorized actuator was exposed. It must not use a warning marker for that intentional
capability boundary.

## Unknown dirty-tree diagnostics contract
- `unknown_dirty_tree` is a hard stop (`manual_review_required`) and must be resolved, not bypassed.
- Finalizer summary output must include bounded path lines with exact path + classification + cleanup result.
- Finalizer JSON artifact must include the full dirty-path diagnostic list with:
  - git status code
  - classification
  - classification source
  - tracked/untracked marker
  - cleanup attempted/result/reason
  - recommended action

## Cleanup ordering contract
When exact task acceptance is supplied, the requested external runtime sandbox is a caller-owned parent namespace whose caller-selected permissions are preserved. Each call exclusively reserves a private `invocations/<collision-resistant-id>/` child, with separate `data/`, `state/`, and `task_acceptance/` directories. The `invocations/` parent and all of those current-invocation descendants are finalizer-owned. Concurrent calls may share the requested parent but never an invocation runtime or acceptance-custody child. The finalizer reads the original mutable manifest and provenance through no-follow regular-file descriptors, exclusively freezes their exact bytes as `task_acceptance/manifest.json` and `task_acceptance/provenance.json`, and verifies those copies before child validation or cleanup. Child stages receive the invocation's data/state mapping explicitly; the finalizer neither uses nor mutates a process-global environment variable for this custody.

Invalid, unstable, non-regular, symlinked, replaced, or permission-ambiguous custody fails closed. On POSIX, finalizer-owned directories require exact mode `0700` and captured files are mode `0600`; an existing finalizer-owned directory with any other mode is rejected before use and is never chmoded, repaired, replaced, deleted, or adopted. Directory type, mode, device, and inode are recorded initially and rechecked without following symlinks before the terminal decision. This check covers the shared `invocations/` parent and only the current invocation's root, `data/`, `state/`, and `task_acceptance/` descendants, not stale children from other calls. On platforms without meaningful POSIX modes, mode enforcement is recorded as not applicable while exclusive creation and no-symlink/type checks remain mandatory. Child stages may overwrite the original provenance and normal generated cleanup may remove an original `glow/` provenance path; initial and terminal acceptance authority uses only the invocation-specific frozen copies, whose bytes, digests, lengths, regular-file identity, and inode/device identity are rechecked before the final decision. Routine finalizer operation therefore does not require a manual `/tmp` provenance copy.

When `--allow-generated-artifact-cleanup` is enabled:
1. run validation stages
2. cleanup/restore known-safe generated byproducts
3. re-read `git status --short`
4. make the final dirty-tree decision

This ordering applies to both pre-commit and pr-metadata phases.

## Runtime reporting, output artifact, and timeouts
- Finalizer progress is deterministic and grep-friendly:
  - `[finalizer] stage start: <stage_id>`
  - `[finalizer] stage end: <stage_id> status=<passed|failed|timed_out> exit_code=<n>`
  - `[finalizer] decision: <status>`
- Summary mode always prints: `Codex Finalize Landing decision: <status>`.
- Use `--output /tmp/codex_finalize_landing.json` to persist conclusive proof on success or failure.
- Use `--stage-timeout-seconds N` for generic stages, `--matrix-timeout-seconds N` for the primary and stale-refresh matrices, and `--overall-timeout-seconds N` as the absolute cap. Defaults are respectively 900, 2400, and 5400 seconds; the remaining overall deadline may reduce a stage's effective timeout.
- Timed out stages return nonzero and classify as `finalizer_failed` (stage timeout) or `environment_blocked` (overall timeout).
- Indeterminate/no-captured-output finalizer runs are not acceptable landing proof.

## Stale evidence refresh
- Validation evidence can become stale after strict-audit repair, runtime artifact restoration, or generated-artifact cleanup.
- Use `--allow-stale-evidence-refresh` to permit an in-task refresh chain:
  - `stale_evidence_matrix_summary`
  - `stale_evidence_matrix_output`
  - `stale_evidence_pr_landing_gate`
  - `stale_evidence_landing_supervisor`
- Refresh is bounded per invocation (`--max-stale-evidence-refreshes`, default `1`) to avoid loops; the finalizer never recursively invokes itself and does not increase retries to escape stale evidence.
- With `--allow-stale-evidence-refresh --max-stale-evidence-refreshes 1`, cleanup-caused staleness has exactly one terminal outcome in that invocation: phase-ready status when refresh succeeds and no blocking dirty paths remain, `stale_evidence_refresh_failed` when a refresh stage fails or times out, or `generated_artifact_cleanup_incomplete` when generated artifacts remain dirty after cleanup.
- `stale_evidence_refresh_required` is reserved for stale evidence when refresh was needed but not allowed. It is not used after a successful bounded refresh.
- The output JSON `evidence_freshness` records `cleanup_occurred`, `cleaned_paths`, `terminal_cleanup_occurred`, `terminal_cleaned_paths`, `stale_evidence_refresh_attempted`, `stale_evidence_refresh_result`, `refresh_stage_runs`, `refresh_stages_ran`, `refreshed_matrix_json_path`, `refresh_failure_reason`, and `rerun_required`; successful bounded refreshes set `rerun_required` to `false` so summaries do not instruct repeated cleanup/refresh reruns.
- Do not rely on stale failed matrix snapshots after strict audits become healthy.

### Canonical pr-metadata command with output
`python scripts/codex_finalize_landing.py finalize --phase pr-metadata --title "[codex:developer] stabilize Codex finalizer runtime reporting" --intended-commit-title "[codex:developer] stabilize Codex finalizer runtime reporting" --matrix-json-path /tmp/work_item_review_packet_matrix.json --focused-test-command "python -m scripts.run_tests -q tests/test_codex_finalize_landing.py tests/test_codex_finalize_landing_script.py tests/test_codex_operating_doctrine_docs.py" --targeted-mypy-command "python -m mypy sentientos/codex_finalize_landing.py scripts/codex_finalize_landing.py sentientos/codex_landing_supervisor.py scripts/codex_landing_supervisor.py sentientos/codex_strict_audit_repair.py scripts/codex_strict_audit_repair.py scripts/run_work_item_review_packet_matrix.py" --allow-docs-bootstrap --allow-strict-audit-repair --allow-generated-artifact-cleanup --stage-timeout-seconds 900 --overall-timeout-seconds 3600 --output /tmp/codex_finalize_landing_pr_metadata.json --summary`

### Troubleshooting long-running stages
1. Identify the last stage-start line with no matching stage-end line.
2. Rerun with higher `--stage-timeout-seconds` for legitimately slow lanes.
3. Use `--output` artifact to inspect per-stage bounded output tails.
4. Repair failing or hung stage command, then rerun finalizer.

## PR metadata guard after finalizer
The pr-metadata/post-commit finalizer is necessary but not sufficient for `make_pr`. After it returns `ready_for_pr_metadata`, run `python scripts/codex_pr_metadata_guard.py verify` with the pre-commit finalizer artifact, pr-metadata finalizer artifact, and matrix artifact. PR metadata is forbidden unless the guard returns `pr_metadata_guard_ready`.

Blocked guard decisions are hard stops. Do not reinterpret a ready finalizer artifact as permission to create PR metadata when `codex_pr_metadata_guard.py verify` reports missing proof, title mismatch, stale evidence, dirty tree evidence, matrix failure, or validation-only mismatch.

## Codex task lifecycle summary artifact

`python scripts/build_codex_task_lifecycle_summary.py` builds a deterministic, metadata-only `codex_task_lifecycle_summary.json` artifact from evidence that already exists. It consumes the pre-commit finalizer JSON, the post-commit/pr-metadata finalizer JSON, the matrix JSON path used for those checks, and optionally the PR metadata guard JSON. It does not rerun tests, matrix lanes, finalizer stages, PR metadata guard checks, shell commands, or cleanup.

The summary emits reviewer/developer workflow fields such as `summary_id`, `task_id`, finalizer statuses, PR metadata guard status, terminal stale-evidence refresh fields, cleanup fields, refreshed matrix path fields, `overall_lifecycle_status`, `rerun_required`, and a non-authority posture block. Missing optional terminal evidence fields are represented as null/unavailable rather than treated as parser failures.

The summary differs from the finalizer: the finalizer remains the executable landing authority that evaluates the tree and validation evidence. The lifecycle summary only records what the finalizer and optional guard artifacts already said. It must not be used as permission to commit, create PR metadata, call `make_pr`, ignore dirty source files, or bypass the two-phase finalizer and PR metadata guard sequence.

Status interpretation is intentionally narrow: `codex_lifecycle_ready` requires `ready_to_commit`, `ready_for_pr_metadata`, and either no guard artifact or `pr_metadata_guard_ready`; any not-ready finalizer, rerun-required finalizer evidence, or non-ready provided guard artifact is `codex_lifecycle_blocked`. Missing or invalid required JSON evidence fails cleanly instead of inventing readiness.

## Codex lifecycle doctor (inspection only)

The Codex lifecycle doctor is a read-only operator inspection CLI:
`python scripts/codex_lifecycle_doctor.py`. It consumes existing JSON artifacts such
as the work-item matrix report, pre-commit finalizer JSON, post-commit/PR-metadata
finalizer JSON, PR metadata guard JSON, lifecycle summary JSON, and run-tests
provenance JSON. It writes an optional deterministic `codex_lifecycle_doctor_report.json`
that explains the currently visible landing state and a next safe inspection action.

The doctor is not a replacement for this finalizer. The finalizer answers whether a
change may advance to commit or PR metadata under landing rules. The lifecycle doctor
answers which available evidence artifact an operator should inspect or rerun next.
Doctor reports are inspection-only evidence: they do not authorize commits, do not
authorize PR creation, do not bypass the finalizer, and do not bypass the PR metadata
guard.

Doctor output exposes ready, blocked, stale, incomplete, and rerun-required states. A
`doctor_ready` result only means the supplied artifacts are mutually consistent from the
doctor's read-only perspective; operators must still require the actual finalizer and PR
metadata guard decisions before commit or PR metadata. Diagnostic/non-proof matrix lanes
remain visible in the doctor matrix summary but are reported as non-blocking unless a
required proof lane failed.

The doctor may also accept `--evidence-index-json <codex_landing_evidence_index.json>`
as a portable manifest. When supplied, the doctor may populate omitted artifact path
arguments from indexed roles such as matrix, pre-commit finalizer, post-commit/PR-metadata
finalizer, PR metadata guard, lifecycle summary, and test provenance. Explicit CLI path
arguments always override index paths. The doctor still opens and reads the underlying
artifact JSON files at the resolved paths, reports missing or invalid referenced artifacts
through its normal incomplete/error rules, and never trusts index aggregate hints as
readiness authority.

## Codex landing evidence index (metadata-only)

`python scripts/build_codex_landing_evidence_index.py` writes `codex_landing_evidence_index.json`, a deterministic metadata-only manifest over already-produced landing evidence artifacts. It records each supplied artifact role, path, existence, JSON readability, raw-byte SHA-256 digest, byte size, schema hint, and status hint. Missing optional paths are represented as `path_not_provided`; supplied paths that do not exist are `path_missing`; existing invalid JSON remains indexed with its digest and an invalid-JSON error.

The evidence index answers: “Which evidence artifacts exist, where are they, what are their digests, and what status hints do they expose?” It differs from the lifecycle summary, which summarizes lifecycle state from specific finalizer/guard evidence; the lifecycle doctor, which advises what an operator should inspect or rerun next; this finalizer, which decides whether a change can advance to commit or PR metadata; the PR metadata guard, which decides whether PR metadata creation is allowed; and the matrix, which reports whether required proof lanes passed.

The index is intentionally non-authoritative. It does not rerun tests, matrix, finalizer, guard, lifecycle summary, doctor, docs, mypy, git, shell commands, provider calls, network calls, or runtime actions. It does not decide `ready_to_commit`, `ready_for_pr_metadata`, or `pr_metadata_guard_ready`, and it cannot authorize commit, `make_pr`, or PR metadata creation. Use it only to pass one portable manifest to inspection tooling while preserving the underlying artifact roles and authoritative checks.

## Codex landing evidence appendix

`python scripts/render_codex_landing_evidence_appendix.py` renders an existing Codex landing evidence index and/or lifecycle doctor report into deterministic markdown for PR bodies, reviewer notes, or operator logs. It is metadata-only, read-only, and non-authoritative. It reads only the JSON paths supplied on the command line and writes markdown plus an optional JSON sidecar; it does not run tests, matrix, docs, mypy, finalizer, PR metadata guard, lifecycle doctor, evidence-index builder, git, network, provider, shell, or runtime actions.

Example:

```bash
python scripts/render_codex_landing_evidence_appendix.py \
  --title "<task title>" \
  --intended-commit-title "<intended commit title>" \
  --evidence-index-json /tmp/codex_landing_evidence_index.json \
  --doctor-report-json /tmp/codex_lifecycle_doctor.json \
  --output /tmp/codex_landing_evidence_appendix.md \
  --json-output /tmp/codex_landing_evidence_appendix.summary.json \
  --summary
```

Evidence index answers: “Which artifacts exist, where are they, what are their digests, and what hints do they expose?” Lifecycle doctor answers: “Using the artifacts, what should an operator inspect or rerun next?” Evidence appendix answers: “How can the current evidence be rendered for reviewers in a compact deterministic markdown format?” Finalizer answers: “Can this change advance to commit/PR metadata under landing rules?” PR metadata guard answers: “Is PR metadata creation allowed?” Matrix answers: “Did required proof lanes pass?”

The appendix can be pasted into PR bodies or operator logs without changing `make_pr`, finalizer, PR metadata guard, or matrix behavior. It never grants commit authority, PR creation authority, runtime authority, readiness, or proof status.

When `--json-output` is supplied, the sidecar records appendix provenance: raw-byte SHA-256 digests, byte sizes, and JSON readability metadata for each supplied input (`--evidence-index-json`, `--doctor-report-json`, and `--doctrine-map-json`), plus the SHA-256 digest and byte size of the rendered markdown bytes. This provenance answers only: “Which exact input files and rendered markdown bytes produced this reviewer surface?” It is tamper-evidence/reviewer provenance only; it does not verify landing authority, artifact freshness, matrix proof, finalizer readiness, PR metadata guard readiness, doctrine authority, model alignment, or reinforcement-learning success. The sidecar intentionally omits a naive digest of its own final file to avoid embedding an unstable self-reference inside itself.
## Beneficial trait doctrine map

The metadata-only [Codex beneficial trait doctrine map](codex_beneficial_trait_doctrine.md) explains which beneficial behavioral traits the existing finalizer, guard, matrix, lifecycle, and evidence rails surface. It is descriptive doctrine only: it does not decide readiness, authorize commits, authorize PR metadata, rerun evidence, or bypass this finalizer.

### Appendix doctrine-map intake

The evidence appendix renderer may include static beneficial-trait context with `--doctrine-map-json PATH`, where `PATH` is JSON emitted by `scripts/build_codex_beneficial_trait_doctrine.py`. The renderer only reads that supplied JSON and renders the **Beneficial Trait Doctrine** section; it does not execute the doctrine builder, run validation, decide readiness, or create PR metadata.

Doctrine rendering is reviewer context only. It explains which beneficial traits are connected to existing landing/evidence rails and how that context can be displayed beside evidence metadata. It does not answer whether a change may commit, whether PR metadata may be created, whether matrix proof passed, whether artifacts are fresh, whether a model is aligned, or whether reinforcement learning succeeded. The finalizer and PR metadata guard remain the landing authorities.
## Codex workcell architecture

The [Codex Workcell Architecture](codex_workcell_architecture.md) places this finalizer inside the bounded SentientOS developer-workflow workcell. The architecture map is descriptive only: it preserves this finalizer as the only commit-readiness authority and does not add runtime authority, scheduling, execution, or new gates.

## Health snapshot boundary

The [Codex Workcell Health Snapshot](codex_workcell_health_snapshot.md) may render supplied finalizer statuses as observed evidence, but it does not create `ready_to_commit`, `ready_for_pr_metadata`, or any other readiness decision. Finalizer authority remains here.

## Pulse contract non-bypass note

The Codex Workcell Pulse Contract may label finalizer pressure from supplied health snapshot metadata, including rerun or stale-evidence observations. It is not landing authority and cannot replace, bypass, or weaken pre-commit finalizer readiness, post-commit/pr-metadata finalizer readiness, or PR metadata guard readiness.

## Daemon recommendation contract note

Daemon recommendation contract output is reviewer context only. It does not replace, bypass, rerun, or satisfy finalizer readiness authority, and it cannot authorize commit or PR metadata. See `docs/development/codex_workcell_daemon_recommendation_contract.md`.
## Workcell memory contract boundary

The Codex Workcell Memory Contract can describe future receipt metadata for finalizer artifacts, but it cannot replace this finalizer, authorize readiness, bypass phase checks, write ledger entries, or create PR metadata authority.

## Memory candidate bundle boundary

The [Codex Workcell Memory Candidate Bundle](codex_workcell_memory_candidate_bundle.md) may include supplied finalizer JSON as candidate review metadata only. Candidate records do not replace this finalizer, do not make stale evidence fresh, do not authorize commit, and do not authorize PR metadata.

## Memory candidate verifier boundary

The [Codex Workcell Memory Candidate Verifier](codex_workcell_memory_candidate_verifier.md) may report candidate bundle structure, but its `verification_status` is never finalizer authority. It cannot replace pre-commit or pr-metadata finalizer decisions, authorize commit, authorize PR metadata, bypass guards, write `/ledger`, or archive `/glow`.

## Memory activation preflight boundary

See [Codex Workcell Memory Activation Preflight](codex_workcell_memory_activation_preflight.md) for the metadata-only future activation prerequisite report. That preflight does not write `/ledger`, archive `/glow`, mutate memory, decide readiness, authorize PR metadata, trigger daemon action, or create active memory authority.

## Vow boundary note

The [Codex Workcell Vow Digest Boundary Contract](codex_workcell_vow_boundary_contract.md) is not finalizer authority. Its digest and alignment summaries cannot decide `ready_to_commit` or bypass this finalizer.

## Vow alignment attestation boundary

The [Codex Workcell Vow Alignment Attestation Bundle](codex_workcell_vow_alignment_attestation.md) is not a finalizer substitute. Its `attested`, `warning`, or `failed` statuses do not authorize commit or bypass finalizer decisions.
## Workcell storage policy boundary

The [Codex Workcell Storage Policy Contract](codex_workcell_storage_policy_contract.md) is not finalizer authority. It must not be used to authorize commit, bypass finalizer checks, or replace current landing evidence.

## Storage policy verifier boundary

See [Codex Workcell Storage Policy Verifier](codex_workcell_storage_policy_verifier.md) for the metadata-only structural verifier for storage policy contracts. Its verification status is not readiness authority and it does not write `/ledger`, archive `/glow`, activate memory, trigger daemons, schedule tasks, or bypass finalizer/PR metadata guard requirements.
## Storage transaction dry-run planner boundary

The [Codex Workcell Storage Transaction Dry-Run Plan](codex_workcell_storage_transaction_plan.md) is the next metadata-only layer for supplied storage policy, candidate, verifier, and vow reports. It emits future `/ledger` and `/glow` would-write plans only; it does not write, archive, activate memory, decide readiness, bypass finalizer/PR metadata guard, trigger daemons, schedule tasks, or create PRs.

## Storage transaction plan verifier boundary

The [Codex Workcell Storage Transaction Plan Verifier](codex_workcell_storage_transaction_plan_verifier.md) is a deterministic metadata-only structural verifier for dry-run storage transaction plans. It checks planned `/ledger` and `/glow` transaction shape, paths, digests, parent-chain gaps, vow alignment context, transaction gaps, reviewer hygiene metadata, future activation requirements, and non-authority posture; it does not write, archive, activate memory, decide readiness, bypass finalizer/PR metadata guard, trigger daemons, schedule tasks, create PRs, or establish federation consensus.
## Storage execution readiness dossier boundary

The [Codex Workcell Storage Execution Readiness Dossier](codex_workcell_storage_execution_dossier.md) may inventory this report as metadata-only evidence for future active-storage design. It does not write `/ledger`, archive `/glow`, activate memory, trigger daemons, decide readiness, authorize PR metadata, or grant runtime storage authority.

## Storage execution dossier verifier boundary

See [Codex Workcell Storage Execution Dossier Verifier](codex_workcell_storage_execution_dossier_verifier.md) for the metadata-only structural verifier that checks dossier evidence inventory, inactive future activation requirements, active execution gaps, reviewer URL hygiene context, and non-authority posture without granting readiness, storage, ledger, glow, daemon, finalizer, PR metadata, commit, task, scheduler, alerting, model-training, or federation authority.

## Storage runtime authority boundary contract note

The [Codex Workcell Storage Runtime Authority Boundary Contract](codex_workcell_storage_runtime_authority_contract.md) records future-only runtime binding requirements for active `/ledger` and `/glow` storage. It is metadata-only and does not grant readiness, finalizer authority, PR metadata authority, runtime write authority, ledger writes, glow archives, daemon action, scheduling, memory mutation, or federation consensus.

## Storage runtime authority verifier boundary

See [Codex Workcell Storage Runtime Authority Boundary Verifier](codex_workcell_storage_runtime_authority_verifier.md) for the metadata-only structural verifier that checks the future-only runtime authority contract without granting readiness, binding runtime authority, writing `/ledger`, archiving `/glow`, mutating memory, scheduling work, triggering daemon action, or establishing federation consensus.

## Storage operator consent request boundary

See [Codex Workcell Storage Operator Consent Request Contract](codex_workcell_storage_operator_consent_contract.md) for the metadata-only future consent request shape. That contract does not collect consent, imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger daemons, decide readiness, authorize commits, or authorize PR metadata.

## Storage operator consent request verifier boundary

See [Codex Workcell Storage Operator Consent Request Verifier](codex_workcell_storage_operator_consent_verifier.md) for the deterministic metadata-only verifier for the future operator consent request shape. The verifier does not collect or imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger daemons, decide readiness, authorize commits, authorize PR metadata, or establish federation consensus.

## Storage operator consent request packet boundary

See [Codex Workcell Storage Operator Consent Request Packet](codex_workcell_storage_operator_consent_request_packet.md) for the deterministic metadata-only future request packet shape. The packet does not present a request, collect or imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger daemons, decide readiness, authorize commits, authorize PR metadata, create PRs, or establish federation consensus.

## Operator consent request packet verifier boundary

The [Codex workcell storage operator consent request packet verifier](codex_workcell_storage_operator_consent_request_packet_verifier.md) is a deterministic metadata-only structural check for request packet JSON. It does not present a request, collect or imply consent, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger `/daemon`, decide readiness, or replace finalizer/PR metadata guard authority.

## Storage operator consent response artifact boundary

The [Codex Workcell Storage Operator Consent Response Artifact Contract](codex_workcell_storage_operator_consent_response_contract.md) defines only the future response artifact schema for explicit `/ledger` and `/glow` consent. It does not create a response artifact, collect or imply consent, bind runtime authority, activate memory, write ledger entries, archive glow evidence, render UI, send messages, trigger daemon action, decide readiness, authorize commits, authorize PR metadata, or create PRs.

## Storage operator consent response verifier boundary

The [Codex Workcell Storage Operator Consent Response Artifact Verifier](codex_workcell_storage_operator_consent_response_verifier.md) is a deterministic metadata-only structural verifier for the future response artifact contract. It creates no response artifact, collects or implies no consent, grants no readiness, storage, ledger, glow, daemon, federation, UI, message, scheduler, commit, PR metadata, or runtime authority, and leaves active storage blocked.

## Storage operator consent evidence dossier boundary

See [Codex Workcell Storage Operator Consent Evidence Dossier](codex_workcell_storage_operator_consent_evidence_dossier.md). The dossier inventories future consent-design evidence only; it does not present a request, collect a response or consent, imply approval, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger `/daemon`, decide readiness, or authorize commit/PR metadata.

## Storage Operator Consent Evidence Dossier Verifier Boundary

See [Codex Workcell Storage Operator Consent Evidence Dossier Verifier](codex_workcell_storage_operator_consent_evidence_dossier_verifier.md). The verifier is deterministic metadata-only structural evidence review; it does not present requests, collect or imply consent, create response artifacts, bind runtime authority, activate storage, write `/ledger`, archive `/glow`, trigger `/daemon`, decide finalizer/PR readiness, or replace missing real-world operator consent.

## Storage Operator Consent Request Presentation Boundary

See [Codex Workcell Storage Operator Consent Request Presentation Boundary Contract](codex_workcell_storage_operator_consent_request_presentation_contract.md). The boundary is deterministic metadata only: request packets, verifier success, evidence dossiers, finalizer readiness, PR metadata guard readiness, matrix passage, daemon recommendations, federation state, runtime authority contracts, storage policy evidence, local files, notifications, displayed copies, and operator silence do not prove presentation, create a response artifact, collect consent, bind runtime authority, or allow active storage.


## Codex landing commit/body binding

The standard landing sequence binds evidence to one exact revision and exact PR body: pre-commit `workspace_binding`, one implementation commit, post-commit `commit_binding`, metadata guard artifact-chain proof, parsed-artifact PR body generation with sidecar, `pr_body_binding_ready`, publication handoff, clean tree/current HEAD check, selected actuator and compatibility preflight, external actuation, independently supplied hosted observation and exact hosted body, hosted-publication custody classification, and separately observed merge state. `pr_publication_handoff_ready` does not imply every actuator is compatible, and compatibility does not prove publication occurred. `ready_to_commit`, `ready_for_pr_metadata`, `pr_metadata_guard_ready`, and `pr_body_binding_ready` are local authorization states, not remote publication. A title/body payload echo is classified as `publication_payload_echo_unverified`, never as a PR. The intended implementation commit, hosted PR head commit, merge commit, and resulting tree are distinct identities: equal trees do not imply equal commits and never satisfy exact-head custody when the hosted SHA was rewritten. See [Codex landing commit/body binding](codex_landing_commit_body_binding.md) for the deterministic custody artifacts and exact status contracts.

## Single-pass matrix execution and generated cleanup

### Per-invocation runtime log custody

Every finalizer invocation reserves a unique external custody root containing private
`data/`, `state/`, `logs/`, and `task_acceptance/` directories. Finalizer child stages
receive `SENTIENTOS_DATA_DIR`, `SENTIENTOS_RUNTIME_STATE_ROOT`, and
`SENTIENTOS_LOG_DIR` pointing at those directories, plus `TRUST_DIR` pointing at
`logs/trust` beneath the same reserved root. The finalizer-owned values override ambient
values in the child environment without changing the parent process environment. Thus
callers do not need to export `TRUST_DIR` (or a general log directory) for landing
evidence to remain clean.

The logs directory has the same private-mode, no-symlink, device/inode identity, external
location, and terminal re-verification custody as the invocation's data and state
directories. `TRUST_DIR` is recorded as a child of that logs root and may be created
lazily by `trust_engine`. `SENTIENTOS_LOG_DIR` also covers the many validation imports
that use `logging_config.get_log_path`; direct feature-specific log environment variables
are not blindly overridden because they can be deliberate application configuration.

This is evidence hygiene for finalizer-owned validation processes, not SentientOS product
runtime logging policy. Repository `logs/` paths are intentionally **not** added to the
generated-artifact exclusions: a repository-local log created outside finalizer custody
remains visible to dirty-tree checks and workspace binding, and therefore blocks landing
unless it is an intended task path.

Each validation pass that executes the landing matrix runs one canonical matrix process with both `--summary` and `--output <matrix-json-path>`. Summary output is presentation layered onto that same matrix execution; it is not a separate full matrix run. Bounded stale-evidence refresh uses the same one-process matrix command before running the PR landing gate and landing supervisor.

Post-commit and PR-metadata phases can still reuse the exact pre-commit matrix binding through `--pre-commit-finalizer-json`; that reuse path performs no new matrix process when the pre-commit finalizer artifact is supplied.

Generated-artifact cleanup distinguishes tracked and untracked paths. Tracked generated artifacts under `glow/`, `pulse/`, `artifacts/codex/`, cache directories, and the runtime privileged audit artifact are restored with `git restore -- <path>`. Untracked generated artifacts are removed with `git clean -fd -- <path>`. Cleanup commands operate on exact argv path arguments, never through shell interpolation, and cleanup never restores or deletes intended task files, undeclared source changes, unknown dirty files, or versioned audit evidence that is not explicitly classified as a safe generated runtime artifact.

## Matrix v2 checkpoint and retry custody

The authoritative matrix writes `sentientos.work_item_review_packet_matrix:v2` custody
atomically after every sequential lane and flushes start/end progress. The contract binds
ordered labels, exact commands and proof classifications; the semantic workspace binding
includes HEAD/tree, intended dirty-file bytes, dependency inputs, interpreter identity,
and the matrix digest while excluding only canonical generated runtime custody. Each child
has a bounded `--command-timeout-seconds`; timeout terminates that child, records the timed
lane, preserves earlier completed lanes, and leaves the timed lane as the resume point.

`--resume-from` validates schema, checkpoint digest, command manifest, semantic workspace,
and contiguous completed results. A passing exact checkpoint returns without execution;
incomplete valid custody resumes its first incomplete lane. Failed required lanes and
stale, reordered, mutated, or differently bound evidence fail closed and cannot be forced.
A pre-commit retry may name its prior finalizer artifact. Exact complete custody records
`exact_precommit_retry_reuse`; incomplete custody is passed to the runner for resume.
Post-commit reuse remains subject to the existing commit transition and metadata/body
bindings.

After a hygiene-only interruption, preserve the checkpoint, remove only the specifically
classified generated path, and retry with the prior finalizer artifact. Never broadly
delete `sentientos_data/`. Generated cleanup does not alter semantic identity, while any
source, command, acceptance, focused-test, mypy, title, lock, or interpreter change rejects
reuse and requires a fresh matrix.

## Solo and exhaustive validation profiles

`--validation-profile solo` is the default. It runs every operator-supplied focused-test and targeted-mypy command, mypy-baseline protection, prompt-boundary verification, strict audits, immutability verification, and workspace/commit binding. Task acceptance is mandatory whenever a manifest is supplied. Documentation dependency and build stages run when documentation, documentation tooling, generated-document inputs, or documentation contracts change; `--force-docs-validation` makes them unconditional. An unchanged documentation surface is recorded as `not_required_for_unchanged_surface`.

`--validation-profile exhaustive` is explicit opt-in for maintenance and release evidence. It preserves matrix-v2, all 131 lanes, checkpoint/resume, semantic workspace binding, lane timeouts, completed-checkpoint reuse, and post-commit custody. Filenames and planner recommendations never escalate `solo`, and solo starts no matrix process.

Each invocation emits a digest-bound `sentientos.landing_validation_plan:v1` artifact containing the requested/effective profile, SHA and phase, title contract, changed-file identity, task-acceptance digests, focused and typing command contracts, required/conditional/skipped stages, results and durations, budgets, matrix status, and overall status. Solo truthfully records `not_requested_for_solo_profile`; it never fabricates matrix success.

After `pr_metadata_guard_ready`, `scripts/build_codex_landing_evidence_body.py` reads that sealed plan from finalizer evidence. Do not pass `--matrix-json-path` for `solo`; the deterministic body records the solo profile and its `not_requested_for_solo_profile` disposition without matrix-success wording. For `exhaustive`, `--matrix-json-path` remains mandatory and must identify passing matrix evidence. The generic metadata verifier must be invoked with the same evidence-backed `--validation-profile`; it does not infer authority from body prose. Both profiles continue through the same exact-byte sidecar and `--verify-body-binding` check.

Solo pre-commit has a 1,200-second total budget and post-commit/PR metadata has 300 seconds, with a 60-second terminal reserve. Positive explicit overrides are allowed. Invalid budgets fail as `landing_budget_invalid`; a stage that would consume the reserve is refused with `stage_budget_exhausted` / `landing_reserve_protected`, without starting a child.

Stages stream prefixed stdout and stderr, retain at most 40 nonblank lines per stream, emit a quiet heartbeat every 30 seconds, and print flushed start/end records. POSIX children run in dedicated sessions; timeout, SIGINT, SIGTERM, and controller exceptions terminate the process group, wait two seconds, then force termination. Windows uses a new process group and the closest available tree termination, but descendant enumeration remains a documented platform limitation. After cancellation or timeout, retain the finalizer artifact and rerun from fresh evidence; do not adopt a still-running child.

Local proportionate proof, commit, and publication never wait for GitHub Actions or another remote status. GitHub provides storage, history, and asynchronous diagnostics rather than landing authority.
