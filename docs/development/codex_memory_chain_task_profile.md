# Codex Memory-Chain Task Profile

This profile is the reusable contract for recurring memory-chain metadata-verification work. It reduces prompt bulk by moving stable requirements into one canonical profile while preserving every executable landing control in `AGENTS.md`, the validation contract, finalizer, PR metadata guard, matrix runner, supervisor, audit tooling, and clean-tree rules.

## When to use this profile

Use this profile for recurring memory-chain work that is metadata-verification, review-packet, fixture-backed, dry-run, sandboxed, or governance-only in nature. Typical tasks add or update candidate/status/decision metadata, deterministic fixtures, review proof surfaces, docs, tests, CLI/module shells, or matrix wiring around the memory-chain subsystem without mutating real live memory.

Do not use this profile to authorize live memory writes, provider invocation, prompt export, external disclosure, host action, action execution, runtime authority expansion, or policy/consent truth. If a prompt needs any of those behaviors, it must say so explicitly and satisfy the separate authority, audit, rollback, panic, and operator-admission requirements in `AGENTS.md`.

## Relationship to AGENTS.md hot-path law

`AGENTS.md` remains the root operating law. This profile only summarizes recurring memory-chain expectations so future prompts can reference a stable profile instead of repeating the same paragraphs. If this profile and `AGENTS.md` conflict, `AGENTS.md` wins.

The hot path is mandatory: bootstrap first; stop on blocked bootstrap artifacts; do not commit on `unknown_dirty_tree` or `manual_review_required`; do not treat focused tests as sufficient when matrix/governance validation is required; require `ready_to_commit` before commit; require `ready_for_pr_metadata` before PR metadata; require `pr_metadata_guard_ready` before `make_pr`.

## Relationship to codex_whole_system_task_template.md

Use this profile together with [`codex_whole_system_task_template.md`](codex_whole_system_task_template.md) for complete subsystem landings. The whole-system template defines the general landing shape; this profile supplies the memory-chain defaults for non-authority boundaries, fixture roots, proof surfaces, and prompt compression.

For explicit surgical repairs, use [`codex_narrow_repair_task_template.md`](codex_narrow_repair_task_template.md) and, when the repair is a recurring memory-chain partial-failure recovery, [`codex_memory_chain_recovery_profile.md`](codex_memory_chain_recovery_profile.md).

## Required bootstrap posture

Run the Codex task bootstrapper before implementation. Implement only from `ready` or `ready_with_warnings` bootstrap output. If bootstrap returns `blocked`, stop and report the blocker; blocked prompt/scaffold artifacts are diagnostic only and must not be used as implementation contracts.

If bootstrap tooling cannot express a root-law documentation touch such as `AGENTS.md`, keep the bootstrap artifact limited to allowed task docs and still obey the prompt's explicit authority to edit `AGENTS.md`; do not reinterpret that limitation as permission to ignore blocked bootstrap output or dirty-tree rules.

## Standard non-authority boundaries

Memory-chain metadata-verification work is not authority. It does not grant or imply:

- consent, policy truth, operator approval, or live memory truth;
- prompt assembly, prompt export, provider invocation, provider SDK use, or network egress;
- action execution, host actuation, external disclosure, federation adoption, transport, sync, merge, install, or runtime apply behavior;
- real live-memory mutation, memory-chain advancement, or privileged runtime mutation.

Receipts, readiness records, proposals, review packets, fixtures, and sandbox outputs are evidence artifacts only unless a separate authorized runtime gate consumes them under its own audited contract.

## Standard no-runtime boundaries

Do not run live memory adapters, advance the memory chain, mutate live memory stores, invoke providers, execute actions, disclose data externally, widen runtime authority, or modify `prompt_assembler.py` unless the task explicitly requests that behavior and provides the required admission, audit, rollback, panic, and operator-authority contract.

Metadata-only, dry-run, sandbox, and review-only code must remain deterministic and local. Test fixtures may model candidates/statuses/decisions, but they must not become runtime writes.

## Standard memory-chain integration expectations

When applicable, memory-chain tasks should make the chain's metadata legible through stable IDs, deterministic candidate/status/decision naming, fixture-backed examples, review-packet evidence, and docs that distinguish metadata evidence from live mutation.

Integration should preserve upstream/downstream dependency order, make blockers explicit, and keep review artifacts reproducible. Any readiness or receipt language must state that it is not adoption, execution, prompt assembly, policy truth, consent, external disclosure, or real memory mutation.

### Sandboxed adapter topology stop rule

The sandboxed live memory commit adapter subchain currently terminates at `sandboxed_live_memory_commit_adapter_envelope`. Later readiness-review metadata in that envelope must not be interpreted as authorization to create `sandboxed_live_memory_commit_adapter_readiness_gate`, `sandboxed_live_memory_commit_adapter_readiness_packet`, `sandboxed_live_memory_commit_adapter_readiness_envelope`, or repeated gate/packet/envelope/readiness ladders. The safe next step after PR #1862 is topology clarification or a repo-native handoff decision, not automatic readiness-gate implementation.

Codex must not generate another sandboxed adapter rung unless repo-native architecture explicitly defines the exact next rung name, upstream evidence key, candidate key, ready decision, terminal handoff target, why the handoff is non-recursive, and why an existing real-root, final-review, or real-readiness rung is insufficient. If a future task proposes a rung by mechanical rename from adapter/gate/packet/envelope/readiness language, stop and run a topology audit instead of implementing. Do not recover failed sandboxed adapter readiness-gate workspaces; when no PR, commit, or patch artifact exists on current main, start fresh from main and audit topology.

The current repo-native topology already contains the real-readiness/final-review/real-root chain and then the sandboxed adapter chain: `real_live_memory_commit_adapter_readiness_gate` -> `real_live_memory_commit_adapter_readiness_envelope` -> `final_live_memory_commit_review_gate` -> `real_memory_root_admission_gate` -> `real_memory_root_admission_packet` -> `sandboxed_live_memory_commit_adapter` -> `sandboxed_live_memory_commit_adapter_gate` -> `sandboxed_live_memory_commit_adapter_packet` -> `sandboxed_live_memory_commit_adapter_envelope`. The sandboxed envelope is the end of that sandboxed branch. Historical sandboxed-readiness decision strings, future flags, safe-next-action labels, deferred-surface labels, or candidate metadata are review markers only; they are not authority to create `sandboxed_live_memory_commit_adapter_readiness_gate` or any repeated sandboxed readiness ladder.

## Required docs/tests/fixtures/CLI/module surfaces

For whole-system memory-chain work, provide the surfaces required by the task prompt and whole-system template:

- module/API surface when behavior is implemented;
- operator-facing CLI when the subsystem has a command surface;
- deterministic tests covering module and CLI behavior;
- public docs and discoverability links when behavior or reviewer workflow changes;
- fixture roots for metadata-verification inputs and expected outputs;
- deterministic artifacts, receipts, manifests, or review packets when the task defines them.

If the task is documentation/governance-only and no Python behavior changes, state that targeted mypy is not applicable because no Python surfaces changed.

## Capability, proof bundle, matrix, and readiness expectations

When a capability landing or changed capability ID is involved, follow [`codex_capability_landing_checklist.md`](codex_capability_landing_checklist.md). Verify capability registry entries, reviewer proof-bundle integration, readiness/index links, matrix lanes, targeted mypy scope, and docs link/index coverage before finalization.

When those surfaces are not applicable, say why. Do not use this profile to reduce proof, capability, matrix, or docs obligations for capability landings.

## Fixture-root ownership expectations

Metadata-verification tasks own only their declared fixture roots. Fixture roots should normally match the capability ID or task slug. Do not edit unrelated fixture roots to make tests pass. Unknown fixture drift must be classified and resolved before commit; generated-expected fixture updates must be deterministic and tied to the task-owned capability or slug.

## Standard validation categories

Run the validation categories required by `AGENTS.md`, the whole-system template, the validation/landing contract, and the task prompt. For memory-chain metadata-verification work, that usually includes:

- focused module/CLI/governance tests;
- docs dependency check and docs build;
- prompt-boundary checks when docs or context-hygiene surfaces are touched;
- strict audit verification and audit immutability verification;
- matrix/landing-gate/supervisor sequence when required by the landing contract;
- targeted mypy for changed Python surfaces, or an explicit not-applicable statement for docs/governance-only work.

## Finalizer and PR metadata guard references

Do not duplicate or weaken the executable landing sequence here. Use [`codex_validation_and_landing_contract.md`](codex_validation_and_landing_contract.md) and [`codex_finalize_landing.md`](codex_finalize_landing.md) for the required two-phase finalizer process, and require the PR metadata guard described there before `make_pr`.

## Standard final report evidence list

Final reports for memory-chain profile tasks should include:

- why the task ran before any live-memory adapter or memory-chain advancement when sequencing matters;
- exact files changed;
- whether Python/tooling changed and targeted mypy applicability;
- profile/template changes and future prompt-compression impact;
- non-negotiable authority, runtime, audit, fixture-root, finalizer, PR metadata guard, clean-tree, and matrix rules that remain intact;
- docs build, prompt-boundary, strict audit, immutability, focused test, matrix/landing gate/supervisor, finalizer, PR metadata guard, clean-tree, and PR metadata results;
- unresolved risks or a statement that none are known.

## Metadata-verification landing evidence and recovery

Memory-chain metadata-verification rungs should treat bootstrap output as the canonical task contract and keep prompts compact. Provide only task deltas that differ from this profile: capability IDs, changed paths, fixtures, blockers, validation deltas, and final-report additions. Do not paste duplicated giant prompt bodies when bootstrap and this profile already define the stable contract.

Generate PR-body evidence with `scripts/build_codex_landing_evidence_body.py` from canonical matrix and landing-supervisor artifacts. The generated body must preserve the matrix output path, unresolved risks, and PR metadata guard markers so late landing failures can be repaired surgically without reconstructing ad hoc PR text.

Recovery handling must be explicit:

- same-workspace recovery can continue when task-owned files, commits, branches, or patch artifacts are present;
- `no-files-found` in a fresh workspace means uncommitted task-owned implementation is not recoverable from the closed task;
- late PR metadata, finalizer, or stale-evidence failures should be repaired in the same task by refreshing canonical evidence and rerunning the finalizer/guard sequence, not by rerunning the whole rung;
- landing-rail repair tasks must not advance the memory chain, invoke executors, assemble prompts, retrieve live context, mutate live memory roots, or enable runtime execution.

## Future prompt compression pattern

Future memory-chain prompts should reference this profile and provide only task-specific deltas where possible:

- task name;
- capability id;
- module/CLI/test/doc/fixture paths;
- upstream dependencies;
- unique candidate/status/decision names;
- unique blockers;
- unique validation deltas;
- unique final report deltas.

Prompts may still expand any section when the task deviates from the standard profile. Deviations must be explicit and cannot override `AGENTS.md`, finalizer, PR metadata guard, matrix, supervisor, audit, clean-tree, fixture-root, or authority-boundary requirements.
