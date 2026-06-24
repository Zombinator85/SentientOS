# Codex landing evidence and recovery rail

This rail hardening covers Codex process failures around late PR metadata and finalizer evidence. It is not a memory-chain advancement path and does not authorize Real Executor Invocation Gate implementation, executor invocation, prompt assembly, live-context retrieval, external disclosure, live-memory mutation, lock acquisition, or runtime flag changes.

## Failure pattern: Real Executor Invocation Gate attempts

The recurring failure pattern was procedural rather than an executor implementation success:

1. A Real Executor Invocation Gate attempt appeared to create task-owned implementation files.
2. The task failed late at PR metadata or finalizer evidence, including missing matrix output references or incomplete PR-body evidence.
3. The task was closed without a PR, commit, branch, or patch artifact that preserved those task-owned files.
4. A later recovery prompt ran in a fresh workspace where the uncommitted files were absent.
5. Recovery was impossible, so a fresh rerun consumed substantial credits and repeated landing-risk conditions.

The fix is to make landing evidence durable and repo-native before PR metadata is attempted. Future tasks should generate the PR body from canonical artifacts instead of reconstructing ad hoc text after a late guard failure.

## No-files-found recovery limit

`no-files-found` means recovery cannot find task-owned files, commits, branches, or patches in the current workspace. In a fresh workspace, uncommitted files from a closed Codex task are not present unless the previous task exported a patch, committed a branch, created a PR, or otherwise produced a durable artifact. A recovery prompt can inspect the current checkout, but it cannot reconstruct files that existed only in a previous ephemeral workspace.

When `no-files-found` is reported, the correct conclusion is that recovery of uncommitted implementation is impossible in that workspace. Do not continue as if missing files are hidden implementation contracts. Either locate a durable artifact or perform a new implementation from the current repo state.

## Canonical PR metadata evidence

PR metadata evidence must be generated from canonical artifacts because the landing gate and PR metadata guard validate concrete evidence, not intent. The durable inputs are:

- the matrix JSON written by `scripts/run_work_item_review_packet_matrix.py --output`;
- the landing supervisor JSON, when already available;
- explicit result text for targeted mypy, baseline, docs build, prompt-boundary checks, strict audit, immutability verifier, finalizer, PR metadata guard, landing gate, and unresolved risks.

Use `scripts/build_codex_landing_evidence_body.py` to produce the PR body. The script writes the required sections, preserves guard-required marker text, and fails if the matrix JSON is missing, the matrix output path marker is absent, the unresolved risks section is absent, or the body is evidence-light.

## Fresh matrix output path

The matrix output path must remain explicit because `matrix_output_reference_missing` is a late PR metadata failure class. A body that claims validation passed but does not name the `--output` artifact is not recoverable enough for reviewers or guard tooling.

The matrix path must also be fresh. If cleanup or later validation changes can make earlier matrix evidence stale, the finalizer may perform one bounded in-invocation refresh of matrix evidence plus landing gate and supervisor evidence when `--allow-stale-evidence-refresh` is supplied. A successful bounded refresh is terminal and may return `ready_to_commit` or `ready_for_pr_metadata`; it must not leave callers with a repeated `stale_evidence_refresh_required` loop. The finalizer does not need to delete `/tmp` matrix output to cause staleness; stale evidence can arise when the evidence no longer reflects the final source tree or post-cleanup state.

## Same-task recovery for late landing failures

For late PR metadata, landing gate, supervisor, or finalizer failures:

1. Keep the task open in the same workspace.
2. Preserve task-owned files and generated evidence paths.
3. Repair only the missing evidence or stale-evidence blocker.
4. Regenerate the PR body with `scripts/build_codex_landing_evidence_body.py`.
5. Rerun the landing gate with the generated body.
6. Rerun the landing supervisor with the fresh matrix JSON.
7. Rerun the two-phase finalizer sequence as required.
8. Run the PR metadata guard and call `make_pr` only after `pr_metadata_guard_ready`.

Do not close the task until a PR exists, a commit/branch/patch artifact exists, or `no-files-found` has been reported and recovery is impossible.

## Distinguishing failure classes

Use stable snake-case labels in task reports and recovery prompts so failures are classified before reruns consume more reviewer or compute time:

- `implementation_failure`: source, docs, fixtures, or tests are missing or failing. Repair task-owned implementation and rerun focused validation before the landing sequence.
- `pr_metadata_failure`: implementation exists, but PR title/body/evidence markers are incomplete. Regenerate the body from canonical artifacts and rerun landing gate/guard.
- `finalizer_stale_evidence_failure`: validation evidence no longer reflects the final tree, often after cleanup or audit repair. Prefer the finalizer's bounded stale-evidence refresh when allowed; if refresh is not allowed, rerun with explicit refresh authority. Treat `stale_evidence_refresh_failed` and `generated_artifact_cleanup_incomplete` as terminal repair statuses, not prompts for unbounded repeated reruns.
- `workspace_state_loss`: a fresh workspace lacks uncommitted files from a closed task. If no commit, branch, PR, or patch artifact exists, report `no-files-found`; do not claim recovery is possible.
- `workspace_contamination_or_absence_gate_failure`: unknown dirty files, missing expected task-owned files, or absence gates block commit until exact paths are resolved or classified.
- `environment_or_dependency_noise`: Python/package setup warnings, dependency chatter, or platform limitations are not implementation evidence unless a required command fails.
- `graph_topology_discovery_failure`: the safe insertion point or handoff topology is unknown. Stop for topology reconstruction instead of creating mechanical repeated rungs.
- `lane_or_matrix_contract_failure`: required lanes, matrix entries, proof maps, or capability wiring are missing or stale. Repair the contract surface and rerun required lanes. Focused or targeted `scripts.run_tests` commands are proof-quality only when selected tests execute and at least one selected test passes; matrix lanes that are intentionally skipped, unsupported, diagnostic, or nonexecuted must be explicitly classified as non-proof and may not satisfy required proof.
- `prompt_bloat_or_repeated_law_failure`: prompts repeat stable law instead of referencing repo doctrine, increasing drift risk. Replace repeated law with references plus task-specific deltas.

## Task classes for prompt shaping

Classify future work before writing prompts:

- `file_anchored_implementation`: concrete files and behavior are known; use the relevant template/profile plus changed paths.
- `topology_reconstruction_or_insertion_point_discovery`: the graph or handoff is uncertain; audit and document topology before implementation.
- `doctrine_metadata_or_landing_repair`: docs/tests/scripts clarify workflow, landing evidence, or guard behavior without adding runtime behavior.
- `local_node_readiness_planning`: local setup is planning-only until a fresh clone, clean baselines, dependencies, and health checks exist.
- `federation_or_distributed_proof_topology`: distributed labor remains proof-sharing and non-duplicative work-claim topology until claim semantics, proof exchange, artifact schema, and authority boundaries are defined.

## Using the generated PR body script

Example:

```bash
python scripts/build_codex_landing_evidence_body.py \
  --title "[codex:landing] harden evidence and recovery rail" \
  --intended-commit-title "[codex:landing] harden evidence and recovery rail" \
  --matrix-json-path /tmp/codex_landing_evidence_recovery_rail_matrix.json \
  --landing-supervisor-json-path /tmp/codex_landing_evidence_recovery_rail_supervisor.json \
  --output /tmp/codex_landing_evidence_recovery_rail_pr_body.txt \
  --targeted-mypy "passed" \
  --baseline "passed" \
  --docs-build "passed" \
  --prompt-boundary "passed" \
  --strict-audit "passed" \
  --immutability-verifier "passed" \
  --finalizer "pre-commit ready_to_commit; post-commit pending" \
  --pr-metadata-guard "pending" \
  --unresolved-risks "None known."
```

The output body includes `Matrix output path: <path>` and `Unresolved risks: <text>`, plus the marker text required by the PR metadata contract. If the landing supervisor JSON is not yet written, the script records the requested path as pending so the body can be used for the landing gate before supervisor evaluation.

## Prompt compression doctrine

Future Codex prompts should reference `AGENTS.md`, `docs/development/codex_open_work_roadmap_index.md`, the relevant profile/template, and task-specific deltas instead of repeating stable law. A compact prompt should provide only the task title, selected roadmap candidate or explicit deviation, fresh-current/current-doctrine requirement, bootstrap command, delta-specific files, delta-specific validation, and unique blockers or authority boundaries.

This compression does not weaken bootstrap, finalizer, PR metadata guard, matrix, supervisor, audit, clean-tree, or authority-boundary requirements. Expand a prompt only when the task deviates from existing doctrine or needs stricter boundaries.

## Topology planning notes

Federation/Genesis Forge distributed coding labor is future proof-sharing and non-duplicative work-claim topology only until claim semantics, proof exchange, artifact schema, and authority boundaries are defined. This rail does not implement routing, task execution, remote work dispatch, adoption, sync, merge, install, or execution behavior.

Codex Windows local-node readiness remains planning-only. Repository mainline state stays canonical until a fresh local clone, clean baselines, dependency readiness, and local-node health checks exist; do not add setup automation from this rail.

## Lifecycle summary artifact for inspection only

For late landing recovery inspection, a task may create `codex_task_lifecycle_summary.json` with `scripts/build_codex_task_lifecycle_summary.py` after the required finalizer and PR metadata guard evidence has already been produced. The artifact consumes existing pre-commit finalizer JSON, post-commit/pr-metadata finalizer JSON, matrix JSON path, and optional PR metadata guard JSON, then emits one compact deterministic summary of lifecycle state.

This helps reviewers see whether the existing evidence says the task is ready, blocked, or requires rerun without rerunning the landing ritual. It is not a recovery rail, authority grant, readiness gate, packet, envelope, or repeated ladder. It cannot repair stale evidence, cannot satisfy missing finalizer or guard proof, and cannot authorize PR metadata when the guard is absent or blocked.

## Lifecycle doctor recovery inspection

When evidence artifacts already exist, the lifecycle doctor may be used to inspect them
without rerunning commands or creating authority. It reads only JSON evidence and can
summarize missing optional evidence as `doctor_incomplete`, required matrix proof
failures as `doctor_blocked`, finalizer freshness problems as `doctor_stale`, and explicit
rerun signals as `doctor_rerun_required`.

Use the doctor to decide what to inspect next, not to recover authority. Lifecycle summary
answers: “What was the lifecycle state from specific finalizer/guard evidence?” Lifecycle
doctor answers: “Given all available evidence artifacts, what should an operator inspect
or rerun next?” Finalizer answers: “Can this change advance to commit/PR metadata under
landing rules?” PR metadata guard answers: “Is PR metadata creation allowed?” Matrix
answers: “Did required proof lanes pass?”

A doctor report is diagnostic-only recovery evidence. It does not replace same-workspace
surgical recovery, does not bless stale finalizer artifacts, and does not create PR
metadata permission.

If a landing evidence index is available, the lifecycle doctor may be invoked with
`--evidence-index-json` so one portable manifest supplies omitted evidence paths. This
index intake is map-only: explicit doctor CLI artifact paths override indexed paths, and
the doctor still reads each resolved matrix/finalizer/guard/lifecycle/test-provenance JSON
artifact before diagnosing incomplete, blocked, stale, rerun-required, or ready states.
Index aggregate hints remain non-authoritative and do not decide readiness.

## Landing evidence index for portable inspection

For late landing recovery, operators may create `codex_landing_evidence_index.json` with `scripts/build_codex_landing_evidence_index.py`. The index is a metadata-only manifest over existing evidence paths: matrix, pre-commit finalizer, post-commit/PR-metadata finalizer, PR metadata guard, lifecycle summary, lifecycle doctor report, and test-run provenance. It helps a recovery prompt or inspection tool receive one manifest instead of several separate path flags.

The index preserves role distinctions. A matrix artifact remains matrix evidence, finalizer artifacts remain finalizer evidence, PR metadata guard artifacts remain guard evidence, lifecycle summary artifacts remain lifecycle-state summaries, doctor reports remain inspection reports, and test provenance remains run provenance. The index records existence, JSON readability, digests, byte sizes, schema hints, and status hints only; it does not convert diagnostic/non-proof lanes into proof and does not turn any hint into authority.

Missing or invalid artifacts are explicit metadata rather than fatal recovery-loss events: omitted optional paths are `path_not_provided`, supplied nonexistent paths are `path_missing`, and invalid JSON records `readable_json: false` with an error while still retaining the raw-file digest. Operators must still inspect or rerun the underlying authoritative artifact according to the lifecycle doctor, finalizer, matrix, and PR metadata guard rules. The index answers: “Which artifacts exist, where are they, what are their digests, and what hints do they expose?” Lifecycle doctor with index answers: “Using the index as a map, what do the underlying artifacts say should be inspected or rerun?”

## Evidence appendix for recovery review

When a recovery task already has an evidence index and/or lifecycle doctor report, `scripts/render_codex_landing_evidence_appendix.py` may render those existing JSON files into a compact markdown appendix. The appendix is a portable review surface for artifact roles, paths, digest short forms, doctor status, matrix proof counts, finalizer/guard hints, test provenance, and non-authority posture.

The distinction is mandatory:

- Evidence index: identifies artifact paths, existence, readable JSON state, digests, and aggregate hints.
- Lifecycle doctor: reads underlying artifacts and reports inspection/rerun guidance without granting authority.
- Lifecycle summary: records lifecycle state from specific finalizer and guard artifacts.
- Evidence appendix: formats already-existing index/doctor evidence as markdown for reviewers.
- Finalizer: decides whether landing may advance to commit or PR metadata under landing rules.
- PR metadata guard: decides whether PR metadata creation is allowed.
- Matrix: records whether required proof lanes passed.

The appendix is recovery evidence only. It does not rerun commands, decide readiness, convert diagnostic/non-proof lanes into proof, bypass finalizer or PR metadata guard, or authorize commit, PR creation, or runtime action.

When a JSON sidecar is requested, appendix provenance records raw-byte SHA-256 digests, byte sizes, and readability metadata for the supplied evidence index, lifecycle doctor report, and doctrine map inputs, and records the rendered markdown digest and byte size. This provenance is reviewer tamper evidence only. It does not replace the evidence index, lifecycle doctor, finalizer, matrix, or PR metadata guard; it does not answer whether artifacts are fresh, proof passed, a commit may land, PR metadata may be created, doctrine is authority, a model is aligned, or reinforcement-learning work succeeded. The sidecar avoids impossible self-reference by not embedding a naive digest of the final sidecar file inside itself.
## Beneficial trait doctrine map

The metadata-only [Codex beneficial trait doctrine map](codex_beneficial_trait_doctrine.md) labels the recovery rail and adjacent landing evidence rails with reviewer-facing behavioral traits such as corrigibility and option-preserving patience. It is not a recovery authority and cannot replace recovery artifacts, finalizer readiness, matrix proof, or PR metadata guard readiness.

### Doctrine context in the appendix

For recovery review, `scripts/render_codex_landing_evidence_appendix.py --doctrine-map-json PATH` may render the static beneficial-trait doctrine map beside existing evidence appendix metadata. This is a compact reviewer aid for connecting recovered evidence rails to stable trait rubrics. It is not recovery authority, readiness proof, matrix proof, freshness proof, model-alignment evidence, or reinforcement-learning evidence.

The appendix does not make doctrine authoritative and does not authorize commit or PR creation. Finalizer readiness and PR metadata guard readiness remain required before landing actions.
## Codex workcell architecture

The [Codex Workcell Architecture](codex_workcell_architecture.md) describes the recovery rail as part of a bounded evidence/review workcell. It does not make recovery evidence a landing authority; finalizer and PR metadata guard authority remain unchanged.

## Health snapshot observation surface

The [Codex Workcell Health Snapshot](codex_workcell_health_snapshot.md) can summarize supplied recovery/evidence metadata for reviewers. It is an observation surface only and cannot recover files, refresh stale evidence, trigger repair, or authorize landing.

## Pulse contract evidence note

The Codex Workcell Pulse Contract may classify evidence recovery pressure observed in a supplied health snapshot, such as missing evidence index, lifecycle doctor, appendix sidecar, or stale refresh signals. These labels are observation-only and do not trigger recovery, daemon repair, alerts, scheduling, or federation action.

## Daemon recommendation contract note

The daemon recommendation contract may identify metadata-only recommendation classes for supplied pulse signals, but recovery authority remains with existing recovery rail procedure. It does not create recovery tasks, schedule work, write ledger entries, or trigger daemon repair. See `docs/development/codex_workcell_daemon_recommendation_contract.md`.
## Workcell memory contract boundary

The Codex Workcell Memory Contract can name future `/ledger` receipt-chain and `/glow` archive roles for recovery evidence, but recovery remains governed by this rail; the memory contract does not archive files or recover task-owned files.

## Memory candidate bundle boundary

The [Codex Workcell Memory Candidate Bundle](codex_workcell_memory_candidate_bundle.md) can summarize supplied recovery and evidence artifacts as candidate `/ledger` and `/glow` records for review. It does not recover files, write archives, mutate memory, create tasks, or bypass recovery and landing rails.

## Memory candidate verifier boundary

The [Codex Workcell Memory Candidate Verifier](codex_workcell_memory_candidate_verifier.md) is review-only evidence about candidate bundle structure. It is not recovery authority, does not recover or mutate files, does not write `/ledger`, does not archive `/glow`, and does not authorize commit, PR metadata, daemon action, task creation, scheduling, or alerts.
