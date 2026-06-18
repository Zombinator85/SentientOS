# Codex Open-Work Roadmap Index

This compact index is the current docs-only pointer for safe non-sandboxed work selection. It is intended to keep future Codex prompts short, prevent repeated architecture rediscovery, and reduce mechanical rung drift. It is not an implementation plan for any blocked surface.

## Current sealed or paused areas

- `sandboxed_live_memory_commit_adapter_envelope` is terminal for the sandboxed adapter branch.
- No post-envelope implementation is authorized from that terminal envelope.
- Do not create a sandboxed readiness gate, readiness packet, readiness envelope, or repeated sandboxed gate/packet/envelope/readiness ladder.
- Future continuation requires a separate complete topology decision that names the exact topology, non-recursive handoff, authority boundary, and why existing real-root/final-review/readiness surfaces are insufficient.

## Recently completed safe validation work

- Phase 97-103 context-hygiene denial-phase coverage is wired into the capability registry, default work-item review packet matrix, validation lane contract, and related tests after PR #1866.
- Treat that wiring as current upstream validation coverage, not as authority to add provider invocation, prompt export, external disclosure, runtime execution, or live-memory mutation.

## Candidate next work tracks

| Candidate track | Status | Allowed scope | Forbidden escalation | Likely files to inspect | Recommended validation commands | Risk level |
| --- | --- | --- | --- | --- | --- | --- |
| Work-item lifecycle attestation matrix/proof consistency audit | Not blocked | Audit-only or docs-only; test-only if existing consistency expectations need coverage | Must not create runtime adoption, new authority, live work-item mutation, or proof-bundle effects beyond review evidence | `docs/development/codex_capability_landing_checklist.md`, `scripts/run_work_item_review_packet_matrix.py`, `scripts/build_work_item_lifecycle_attestation_index.py`, `tests/test_work_item_lifecycle_attestation_review_digest.py`, `tests/test_work_item_lifecycle_attestation_review_digest_index_verifier.py` | `python -m scripts.run_tests -q tests/test_work_item_lifecycle_attestation_review_digest.py tests/test_work_item_lifecycle_attestation_review_digest_index_verifier.py`; `python scripts/build_docs.py --check-deps`; `python scripts/build_docs.py` | Medium |
| Workspace change-set preflight proof coverage audit | Not blocked | Audit-only, docs-only, or test-only around existing preflight proof coverage | Must not perform workspace mutation, admission execution, preflight execution side effects, runtime apply, or closure helper invocation | `tests/test_workspace_change_set_admission.py`, workspace change-set docs under `docs/`, existing workspace change-set scripts/modules referenced by tests | `python -m scripts.run_tests -q tests/test_workspace_change_set_admission.py`; `python scripts/verify_context_hygiene_prompt_boundaries.py`; `python scripts/build_docs.py --check-deps`; `python scripts/build_docs.py` | Medium |
| Landing evidence recovery prompt/body repetition reduction | Not blocked | Docs-only or metadata-only; test-only for existing PR-body evidence generation behavior | Must not bypass finalizer, PR metadata guard, matrix, supervisor, audit, clean-tree, or recovery-law requirements | `docs/development/codex_memory_chain_task_profile.md`, `docs/development/codex_memory_chain_recovery_profile.md`, `docs/development/codex_finalize_landing.md`, `docs/development/codex_validation_and_landing_contract.md`, `scripts/build_codex_landing_evidence_body.py`, `scripts/codex_pr_metadata_guard.py` | `python -m scripts.run_tests -q tests/test_codex_operating_doctrine_docs.py`; `python scripts/verify_context_hygiene_prompt_boundaries.py`; `python scripts/build_docs.py --check-deps`; `python scripts/build_docs.py` | Low |
| Host-boundary deferred/blocked host-actuation label audit | Partially blocked | Audit-only or docs-only; test-only if labels already exist and remain non-authority | Must not add direct host actuation, fan/PWM/thermal writes, executor authority, admission grants, rollback actions, or panic-path behavior | `AGENTS.md`, `docs/REMOTE_HOST_SMOKE_LAB.md`, `docs/REMOTE_SMOKE_CI_LANE.md`, `docs/REMOTE_PROBES.md`, host-boundary tests found with `rg "host-actuation|host actuation|fan|PWM|thermal|deferred" docs tests scripts sentientos` | `python -m scripts.run_tests -q tests/test_codex_operating_doctrine_docs.py`; `python scripts/verify_context_hygiene_prompt_boundaries.py`; `python scripts/build_docs.py --check-deps`; `python scripts/build_docs.py` | Medium |
| Context-hygiene denial-phase documentation consolidation | Not blocked | Docs-only or audit-only around existing Phase 97-103 denial-phase surfaces | Must not add new denial-phase behavior, prompt assembly, prompt export, provider invocation, external disclosure, or runtime authority | `docs/architecture/context_hygiene_spine.md`, `docs/development/codex_validation_and_landing_contract.md`, `scripts/verify_context_hygiene_prompt_boundaries.py`, tests covering Phase 97-103 context-hygiene denial capabilities | `python scripts/verify_context_hygiene_prompt_boundaries.py`; `python -m scripts.run_tests -q tests/test_codex_operating_doctrine_docs.py`; `python scripts/build_docs.py --check-deps`; `python scripts/build_docs.py` | Low |

## Blocked task classes

Do not select these classes from this roadmap:

- Post-envelope sandboxed adapter continuation without a complete topology decision.
- Any sandboxed readiness gate, readiness packet, readiness envelope, or repeated sandboxed ladder.
- Any task that grants runtime, executor, lock, live-memory, root, admission, adapter, host-actuation, external disclosure, or authority behavior.
- Any task that attempts to recover failed readiness-gate workspaces or blocked scaffolds.
- Any task that treats metadata-only, dry-run, sandbox, review-only, readiness, receipt, or proposal evidence as live authority.

## Prompt compression rule

Future "next" prompts should reference this roadmap index and provide only:

- task title;
- selected roadmap candidate or explicit deviation;
- fresh-current/current-doctrine requirement;
- bootstrap command;
- delta-specific files;
- delta-specific validation;
- unique blockers or authority boundaries.

Reference `docs/development/codex_landing_evidence_recovery_rail.md` for failure classes, task classes, same-workspace recovery, local-node-readiness planning, and distributed-proof topology notes. Expand the prompt only when the selected candidate deviates from this index or requires stricter boundaries. No prompt may use this index to override `AGENTS.md`, bootstrap, finalizer, PR metadata guard, matrix, supervisor, audit, clean-tree, or authority-boundary requirements.
