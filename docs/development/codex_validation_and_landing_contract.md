# Codex Validation and Landing Contract

## Two-phase finalizer contract
1. Before commit, run `python scripts/codex_finalize_landing.py finalize --phase pre-commit ...`.
   - Commit only if status is `ready_to_commit`.
   - Intended source/doc/test changes may be present when declared via `--changed-file`, inferred from tracked changes with `--allow-current-tracked-changes`, and inferred from safe untracked task files with `--allow-current-task-files` (pre-commit only).
2. After commit and before PR metadata/final report, run `python scripts/codex_finalize_landing.py finalize --phase pr-metadata ...` (or `post-commit`).
   - Create/update PR metadata only if status is `ready_for_pr_metadata`.
   - Tree must be clean except allowed generated artifacts that are cleaned successfully.

## Required evidence
Run the validation required by `AGENTS.md`, the task profile/template, and the changed surfaces. Focused tests alone are insufficient when matrix, governance, landing, audit, supervisor, proof, or capability rails apply.

The mandatory landing sequence remains: bootstrap -> required validation -> pre-commit finalizer `ready_to_commit` -> commit -> post-commit/pr-metadata finalizer `ready_for_pr_metadata` -> PR metadata guard `pr_metadata_guard_ready` -> `make_pr`.

Situational validation selects the relevant lanes without weakening the landing contract:

- docs build when docs changed;
- prompt-boundary checks when context-hygiene or prompt-boundary docs/scripts are touched;
- targeted mypy when Python surfaces changed;
- lane/matrix/capability tests when those surfaces changed;
- broader regression at threshold/risk points or when required by existing doctrine.

For context-hygiene denial-phase documentation touching Phase 97-103 posture, treat the coverage as validation-only and non-runtime. The reviewer-facing consistency lane is `python scripts/verify_context_hygiene_prompt_boundaries.py` plus `python -m scripts.run_tests -q tests/test_capability_registry.py tests/test_work_item_review_packet_matrix.py`; docs edits still require `python scripts/build_docs.py --check-deps` and `python scripts/build_docs.py`. These checks confirm capability registry, matrix, verifier, spine, and validation-contract discoverability only; they do not grant provider invocation, prompt assembly, prompt export, external disclosure, release unblock, runtime authority, routing, admission, execution, or live `assemble_prompt(...)` behavior.

Run `python scripts/codex_landing_supervisor.py evaluate --title "..." --intended-commit-title "..." --matrix-json-path /tmp/work_item_review_packet_matrix.json --summary` after matrix and PR gate when the landing rail requires supervisor evidence; do not finalize unless decision is `ready_to_commit` or `ready_for_pr_metadata`.

## Dirty tree rules
- Pre-commit: declared intended task changes are allowed.
- Post-commit/pr-metadata: source dirty files block.
- Unknown dirty files always block.
- Generated runtime artifacts must be cleaned or block.
- Generated-artifact cleanup can make prior matrix/gate/supervisor evidence stale. When stale-evidence refresh is allowed, the finalizer performs one bounded refresh and must return a terminal status from that invocation. Successful refresh can permit `ready_to_commit`/`ready_for_pr_metadata`; failed refresh or leftover generated artifacts block with explicit terminal statuses.


## Self-sealing requirement
- Validation-only seal turns should not be necessary for normal implementation tasks.
- If finalizer tooling is available, the same task must self-seal using both phases.
- Missing post-commit/pr-metadata finalizer before PR metadata is a task-owned failure.
- Missing stale-evidence refresh in the same task (when strict-audit/cleanup state changed) is task-owned failure. Allowed stale-evidence refresh must be bounded to one terminal finalizer outcome rather than repeated cleanup/refresh cycles.
- Do not request a validation-only follow-up when the only blocker is stale matrix/gate/supervisor/finalizer evidence.
- Do not defer post-commit sealing to follow-up turns when implementation changes occurred.

## Bootstrap and PR metadata guard hard stops
- Run the bootstrapper before implementation. If bootstrap status is `blocked`, generated prompt/scaffold artifacts are diagnostic only and must include `BLOCKED_DO_NOT_IMPLEMENT`; stop, report the blocker, and do not implement, commit, or `make_pr` from that artifact.
- Implement only from `ready` or `ready_with_warnings` bootstrap output.
- After the post-commit/pr-metadata finalizer returns `ready_for_pr_metadata`, run `python scripts/codex_pr_metadata_guard.py verify ...` and require `pr_metadata_guard_ready` before PR metadata or `make_pr`.
- A finalizer artifact alone is not enough when the PR metadata guard says blocked.
- Focused tests passing without a ready PR metadata guard is not a complete landing.

Strict landing sequence: run bootstrapper; stop if blocked; implement only if ready/ready_with_warnings; run required validation; run pre-commit finalizer and require `ready_to_commit`; commit; run post-commit/pr-metadata finalizer and require `ready_for_pr_metadata`; run PR metadata guard and require `pr_metadata_guard_ready`; only then `make_pr`.

## Metadata-only lifecycle summaries

A Codex task lifecycle summary may be produced as a developer workflow artifact after validation/finalizer/guard evidence exists. The summary consumes already-produced finalizer JSON artifacts, the matrix JSON path, and optional PR metadata guard JSON. It emits deterministic metadata including finalizer decisions, optional PR #1878 terminal freshness fields, cleanup fields, guard status, lifecycle status, rerun reason, and explicit non-authority posture flags.

The summary is evidence only. It does not replace bootstrap, validation, matrix, supervisor, pre-commit finalizer, post-commit/pr-metadata finalizer, PR metadata guard, clean-tree checks, commit requirements, or `make_pr` requirements. If the summary reports `codex_lifecycle_ready`, that means only that the supplied artifacts contain ready statuses; the executable landing sequence still controls.

## Lifecycle doctor and validation evidence boundaries

The Codex lifecycle doctor is a deterministic inspection surface over existing landing
artifacts. Inputs may include matrix JSON, finalizer JSON from both phases, PR metadata
guard JSON, lifecycle summary JSON, and `scripts.run_tests` provenance JSON. Outputs
include `doctor_report_id`, evidence path summaries, matrix proof counts, blocked lane
summaries with `proof_status` and `exit_reason`, finalizer freshness fields, test
provenance proof-quality classification, a next safe action, and an explicit
non-authority posture.

The doctor must not run validation, tests, matrix lanes, finalizer commands, guard
commands, docs commands, mypy, git, network calls, provider calls, shell commands, or
runtime actions. It marks missing requested evidence as incomplete and invalid JSON as a
clean CLI error. It must not infer readiness from title or intended commit title alone.
It may accept `--evidence-index-json` to populate omitted artifact path arguments from a
portable evidence-index manifest, but explicit CLI paths override index paths and the
doctor must still read the resolved underlying artifact JSON files. Index aggregate hints
are inspectability metadata only and cannot decide readiness.

Diagnostic/non-proof matrix lanes appear in doctor output for visibility, including
non-proof failures and exit reasons, but they are not blocking when `required_failure_count`
is zero and no required proof lane has a non-passing `proof_status`. Required proof lane
failures remain blocking and must be repaired or rerun through the authoritative matrix
and landing flow.

## Evidence index boundary

The Codex landing evidence index is a deterministic manifest for developer-workflow evidence. It may be produced after evidence artifacts exist so operators can pass one JSON file to future inspection tooling. It records artifact roles, paths, presence, JSON readability, raw-byte digests, optional schema/status hints, aggregate hints, and explicit non-authority posture flags.

The distinction is mandatory:

- Evidence index: identifies which evidence artifacts exist, where they are, their digests, and their status hints.
- Lifecycle doctor with index: uses the index as a map, then reads the underlying artifacts to report what an operator should inspect or rerun next.
- Lifecycle doctor without index: given explicit evidence artifact paths, reports what an operator should inspect or rerun next.
- Lifecycle summary: records lifecycle state from specific finalizer and guard evidence.
- Finalizer: decides whether the change may advance to commit or PR metadata under landing rules.
- PR metadata guard: decides whether PR metadata creation is allowed.
- Matrix: reports whether required proof lanes passed.

The evidence index must not replace or weaken bootstrap, validation, matrix, supervisor, finalizer, PR metadata guard, clean-tree requirements, commit requirements, or `make_pr` requirements. Missing optional artifacts and invalid JSON are represented in the index for visibility only; they do not become proof and must be handled by the authoritative tools that consume the underlying artifacts.

## Evidence appendix review surface

A Codex landing evidence appendix can be generated from existing evidence index and/or lifecycle doctor JSON with `scripts/render_codex_landing_evidence_appendix.py`. It creates deterministic markdown for PR bodies, reviewer notes, or operator logs and can optionally write a deterministic metadata sidecar with `--json-output`.

The appendix is not a validation lane and not a landing authority. Missing optional inputs render as “not provided”; supplied missing or invalid JSON paths fail cleanly. The renderer does not run `scripts.run_tests`, the matrix, docs, mypy, finalizer, PR metadata guard, lifecycle doctor, evidence index builder, git, network, provider, shell, or runtime commands.

Required distinction for reviews:

- Evidence index answers: “Which artifacts exist, where are they, what are their digests, and what hints do they expose?”
- Lifecycle doctor answers: “Using the artifacts, what should an operator inspect or rerun next?”
- Evidence appendix answers: “How can the current evidence be rendered for reviewers in a compact deterministic markdown format?”
- Finalizer answers: “Can this change advance to commit/PR metadata under landing rules?”
- PR metadata guard answers: “Is PR metadata creation allowed?”
- Matrix answers: “Did required proof lanes pass?”

The appendix may be pasted into PR bodies or operator logs, but doing so does not change `make_pr`, finalizer, PR metadata guard, matrix, clean-tree, or proof requirements.

With `--json-output`, the appendix sidecar also records metadata-only provenance: raw-byte SHA-256 digests, byte sizes, and readability metadata for each supplied input JSON file and a SHA-256 digest/byte size for the rendered markdown output. Appendix provenance answers: “Which exact input files and rendered markdown bytes produced this reviewer surface?” It does not answer whether a change may commit, whether PR metadata may be created, whether matrix proof passed, whether artifacts are fresh, whether doctrine is authority, whether a model is aligned, or whether RL training succeeded. To avoid unstable embedded self-reference, the sidecar documents that a naive digest of the final sidecar file is intentionally omitted.
## Beneficial trait doctrine map

The metadata-only [Codex beneficial trait doctrine map](codex_beneficial_trait_doctrine.md) provides a static rubric for how existing validation and landing rails support reviewer-facing behavioral traits. It does not change this contract, add a gate, decide matrix success, authorize commits, or authorize PR metadata.

### Doctrine context in evidence appendix

The evidence appendix can optionally render beneficial-trait doctrine context by passing `--doctrine-map-json PATH` to `scripts/render_codex_landing_evidence_appendix.py`. This reads an already-built doctrine map JSON and adds deterministic reviewer tables for doctrine posture, trait catalog, rail-to-trait mappings, and trait-to-rails index.

This appendix mode is review context only. It does not make doctrine authoritative, add a validation gate, decide matrix success, authorize commits, authorize PR creation, establish artifact freshness, infer model alignment, or claim reinforcement-learning outcomes. The finalizer and PR metadata guard remain the only landing authority for commit and PR metadata phases.
## Codex workcell architecture

The [Codex Workcell Architecture](codex_workcell_architecture.md) summarizes how validation, proof, review, doctrine, finalizer authority, PR metadata guard authority, and future ledger/glow/pulse/daemon/federation surfaces fit together. It is metadata-only doctrine and does not change this validation and landing contract.

## Health snapshot is not a landing gate

The [Codex Workcell Health Snapshot](codex_workcell_health_snapshot.md) is a cockpit/vitals rendering of supplied metadata artifacts. It is not a validation lane, readiness gate, finalizer replacement, PR metadata guard replacement, or authority source.

## Pulse contract validation boundary

The Codex Workcell Pulse Contract is a deterministic metadata catalog for pressure signal names and categories. It does not add a landing gate, does not decide matrix success, does not authorize commits or PR metadata, and does not make skipped, nonexecuted, timed-out, stale, or missing proof count as validation.

## Daemon recommendation contract note

Daemon recommendation contract artifacts are non-authoritative review surfaces. They do not create validation lanes, decide readiness, bypass the finalizer, bypass the PR metadata guard, or authorize commit/PR metadata. See `docs/development/codex_workcell_daemon_recommendation_contract.md`.
## Workcell memory contract boundary

The Codex Workcell Memory Contract defines future metadata shapes for landed evidence history and archive review surfaces. It does not add validation gates, satisfy matrix lanes, authorize commit, authorize PR metadata, or bypass required finalizer and guard checks.

## Memory candidate bundle boundary

The [Codex Workcell Memory Candidate Bundle](codex_workcell_memory_candidate_bundle.md) is a deterministic review surface over supplied artifacts. It does not add validation lanes, satisfy matrix proof, bypass finalizer or PR metadata guard authority, authorize commit, authorize PR creation, write ledger entries, archive glow items, or create runtime authority.

## Memory candidate verifier boundary

The [Codex Workcell Memory Candidate Verifier](codex_workcell_memory_candidate_verifier.md) can emit `memory_candidate_bundle_verified` for structural candidate consistency, but that status is not validation, matrix, finalizer, supervisor, PR metadata guard, clean-tree, commit, or PR authority. It does not write `/ledger`, archive `/glow`, mutate memory, trigger daemons, schedule work, create tasks, alert, train models, or establish federation consensus.

## Memory activation preflight boundary

See [Codex Workcell Memory Activation Preflight](codex_workcell_memory_activation_preflight.md) for the metadata-only future activation prerequisite report. That preflight does not write `/ledger`, archive `/glow`, mutate memory, decide readiness, authorize PR metadata, trigger daemon action, or create active memory authority.

## Workcell vow boundary contract

The [Codex Workcell Vow Digest Boundary Contract](codex_workcell_vow_boundary_contract.md) records canonical forbidden-inference constraints for `/vow`. It does not add validation gates, satisfy matrix proof, decide readiness, authorize commit, authorize PR metadata, or bypass finalizer/guard authority.

## Vow alignment attestation boundary

The [Codex Workcell Vow Alignment Attestation Bundle](codex_workcell_vow_alignment_attestation.md) is a metadata-only review artifact. It does not replace validation, matrix proof, supervisor decisions, finalizer readiness, PR metadata guard readiness, clean-tree checks, commits, or `make_pr`.
## Workcell storage policy boundary

The [Codex Workcell Storage Policy Contract](codex_workcell_storage_policy_contract.md) is not validation, matrix, finalizer, or PR metadata guard authority. Its policy status must not be treated as readiness.
