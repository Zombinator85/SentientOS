# SentientOS Repository Agent Map

Project purpose and contributor orientation: read the [canonical README](README.md), [project thesis](docs/architecture/sentientos_project_thesis.md), and [current source-bound system map](docs/architecture/system_atlas_index.md) before making architecture claims. Preserve the distinction between intended development, implemented composition, and demonstrated outcomes.

SentientOS prioritizes operator accountability, auditability, and safe shutdown. Privileged actions and consequential effects require attributable evidence.

## Canonical governance

Current agent taxonomy, privilege contracts, federation rules, procedures, and evidence requirements are indexed by [`docs/GOVERNANCE_DOCTRINE.md`](docs/GOVERNANCE_DOCTRINE.md). Changes to agent privilege must cite their authority source and update the canonical ledger. Compatibility invocations of `bless`, `animate`, or `reflect` continue to log to `/logs/privileges/`.

## Operator and authority boundaries

- Preserve local operator authority and fail closed on ambiguous privileged action.
- Do not add provider invocation, provider SDKs, prompt export, network egress, external disclosure, or runtime provider authority unless explicitly requested.
- Do not add direct host actuation without control-plane admission, audit, rollback, panic, and operator authority. Phase 1 host resource work is read-only; never add fan/PWM/thermal writes without explicit authority.
- Federation evidence, receipts, readiness, proposals, metadata-only work, dry runs, sandboxes, and review evidence are not adoption, consent, policy truth, transport, sync, merge, apply, installation, execution, or live-memory mutation authority.

## Default Codex workflow: autonomous development

**Operator-requested development is authorized to proceed immediately.** The default is to build, experiment, repair, and iterate; formal acceptance is an opt-in release activity, not a prerequisite for ordinary engineering. This default supersedes mandatory bootstrap, matrix, landing, and PR-ceremony language elsewhere in the developer workflow documents unless the operator explicitly selects formal acceptance.

1. Inspect the relevant current code and existing changes, then implement. Do not require a fresh prompt-bound SHA, a clean initial worktree, a bootstrap scaffold, a declared file allowlist, or an authorization ritual before ordinary coding. Do not overwrite unrelated work.
2. Modify any task-relevant source, configuration, tests, docs, scripts, or developer-governance files. Make coherent commits incrementally; the agent may maintain and revise its own developer tooling.
3. Run the smallest useful local check when practical; favor focused tests and direct behavior checks. Full pytest, mypy, exhaustive matrices, strict audits, docs builds, immutability verification, test-acceptance manifests, and two-phase finalizers are **not default gates**. If checks are skipped or fail, state that accurately and keep working on independent tasks. Do not disguise a failure as a pass.
4. PRs, metadata guards, exact PR-body binding, publication handoffs, and independent hosted-custody attestations are optional for development. Push or open a PR when the operator wants to share work and the environment supports it. Direct commits/merges are allowed where GitHub permissions and settings permit them; never bypass platform-enforced access controls.
5. When a proxy, CI runner, package index, connector, or transport fails, diagnose briefly, preserve existing work, report the limitation once, and continue useful development. Do not repeatedly retry a known failure, rerun completed inference, or create elaborate backup ceremonies merely to satisfy developer-workflow paperwork.
6. Preserve original scientific observations, preregistered artifacts, relevant digests, and historical commits. Corrections are new versioned records; never silently replace a recorded observation or falsely claim model identity, verification, publication, or test success.
7. Consequential live effects, secrets, protected host access, production activation, and changes to runtime privileges still require the operator authority specified above. Permission denial is not a coding challenge to bypass.

### Formal acceptance and release (only when requested)

For an operator-requested production promotion, strict attestation, protected-state change, or release, use [the validation/landing contract](docs/development/codex_validation_and_landing_contract.md), [finalizer reference](docs/development/codex_finalize_landing.md), and currently enforced GitHub checks. Their detailed gates apply **only in that selected mode**. Failing to complete formal publication does not erase a completed local experiment or forbid continued development.

### Nonprivileged engineering continuity

Make reasonable, authorized environment repairs and continue unrelated work when a dependency remains blocked. Distinguish code defects from environment limitations, and retain a concise failure record. Do not elevate privileges or bypass an explicit access denial.

## Repository navigation

- Active work and sealed boundaries: [`docs/development/codex_open_work_roadmap_index.md`](docs/development/codex_open_work_roadmap_index.md)
- Whole-system task shape: [`docs/development/codex_whole_system_task_template.md`](docs/development/codex_whole_system_task_template.md)
- Narrow repair shape: [`docs/development/codex_narrow_repair_task_template.md`](docs/development/codex_narrow_repair_task_template.md)
- Validation and landing policy: [`docs/development/codex_validation_and_landing_contract.md`](docs/development/codex_validation_and_landing_contract.md)
- Executable landing reference: [`docs/development/codex_finalize_landing.md`](docs/development/codex_finalize_landing.md)
- Evidence recovery: [`docs/development/codex_landing_evidence_recovery_rail.md`](docs/development/codex_landing_evidence_recovery_rail.md)
- Capability checklist: [`docs/development/codex_capability_landing_checklist.md`](docs/development/codex_capability_landing_checklist.md)
- Memory-chain profiles: [`docs/development/codex_memory_chain_task_profile.md`](docs/development/codex_memory_chain_task_profile.md) and [`docs/development/codex_memory_chain_recovery_profile.md`](docs/development/codex_memory_chain_recovery_profile.md)

## Optional verification commands

Use proportionate checks when they add confidence:

- `python -m scripts.run_tests -q <focused-test-path>` (or `python -m scripts.run_tests -q` for a broader sweep)
- `python -m mypy scripts/ sentientos/`
- `python verify_audits.py --strict`
- `python scripts/audit_immutability_verifier.py`

The previous "construction mode" is now the normal development mode. Label unfinished or untested results truthfully in reports; there is no mandatory `[untested]` commit-title ritual. Formal acceptance can be performed later without preventing intervening coding work.

## Commit and PR title

Prefer `[codex:<subsystem>] <intent summary>` for discoverability, but titles are not an authorization gate.
