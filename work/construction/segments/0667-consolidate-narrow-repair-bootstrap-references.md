# Sequence 667: Consolidate narrow repair bootstrap references

The narrow repair template repeated bootstrap CLI flags, unsupported-flag handling, and the stop-on-blocked rule already maintained in the canonical bootstrap invocation contract. The documentation-only change shortens that section to references to the canonical contract and `AGENTS.md`, preserving both boundaries.

The documentation dependency check and 616-page build passed. The focused developer-doctrine suite passed 4/4. The repository-wide prompt boundary scan passed with zero findings, and `git diff --check` passed. The required local pre-commit finalizer did not become ready: strict audit and audit immutability each returned `Access denied: run as Administrator to reach protected memory and policy state`; an elevated retry did not change that result. The finalizer also reported undeclared construction evidence paths, which can be bound explicitly in a normal finalizer attempt. Both exact outputs are preserved with this record.

An exploratory mypy-baseline refresh was not implemented: its bootstrap returned `blocked` because the existing-target maintenance scope does not admit `vow/mypy_baseline.json`. The diagnostic artifact was not used as an implementation contract. The repository-wide mypy check itself used version 1.20.2, found zero new errors, and reported 42 retired records; no baseline was changed.

Base main: `00b8cc00e5d1b30e892fe380ec95bb6978f17712`, tree `c68ad621fa6797f92febfa25b42f597629bf6884`.
The repository's explicit bounded-construction exception permits this candidate to proceed only with `[untested]` in its commit title and handoff. The local finalizer result remains blocked and must be reported. Exact hosted Quality Gate, CI, and post-merge checks are still required before merge or any validation claim.

Evidence: `work/construction/evidence/0667-consolidate-narrow-repair-bootstrap-references.json`.
