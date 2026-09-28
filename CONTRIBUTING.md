# Contributing to SentientOS

Contributions preserve local operator authority, attributable evidence, safe shutdown, immutable historical evidence, and fail-closed privileged action. [`AGENTS.md`](AGENTS.md) is repository law for automated work; the [validation and landing contract](docs/development/codex_validation_and_landing_contract.md) and [executable finalizer reference](docs/development/codex_finalize_landing.md) are canonical.

## Contribution lifecycle

1. Bind to a clean, fresh current SHA and record it.
2. Run the supported task bootstrap. Stop if its repository-defined decision is `blocked`; diagnostic scaffolds confer no implementation authority.
3. Make one complete bounded change without expanding provider, network, host-actuation, or prompt-export authority.
4. Supply versioned exact-node acceptance for behavior-adding work, including a successful-path node. Run focused behavioral proof, the applicable matrix, targeted mypy, documentation/prompt checks, strict audits, and immutability verification.
5. Run the pre-commit finalizer and require `ready_to_commit`; commit exactly once.
6. Run the post-commit finalizer and require `ready_for_pr_metadata`, then require `pr_metadata_guard_ready`.
7. Generate the canonical PR body, bind its exact bytes, and seal `pr_publication_handoff_ready` before the one external PR publication call.
8. Treat publication readiness and an actuator payload echo as non-proof. Only an independent exact hosted observation closes publication custody.

Do not copy the complete machine ritual here; follow the linked canonical commands because they evolve.

## Engineering boundaries

- Capability definition, grant, feasibility, admission, execution, observation, receipt, and adoption are separate.
- Tests, dry runs, proposals, synthetic providers, and metadata are not production effects.
- Cognition consumes authority; it does not mint authority for itself.
- Preserve prior atlases, dockets, release evidence, and compatibility identifiers required by protocols.
- Never put `try`/`catch` around imports. Do not modify `prompt_assembler.py` without explicit authority.
- Historical Lumos, First Wound, ritual, Cathedral, Council, and Oracle conventions are not the universal contribution contract. Retain them only where current compatibility law requires them.

## Core checks

```bash
python -m scripts.run_tests -q
python -m mypy scripts/ sentientos/
python scripts/build_docs.py --check-deps
python scripts/build_docs.py
python verify_audits.py --strict
python scripts/audit_immutability_verifier.py
```

Use targeted scope and the task-specific matrix/acceptance manifest exactly as the canonical contract requires; aggregate counts alone are not behavioral proof. Commit and PR titles use `[codex:<subsystem>] <intent summary>`.
