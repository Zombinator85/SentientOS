# Sequence 592 — retained outcomes require the currently observed model identity

PR #2641 extends the receipt-backed canonical-planning regression after sequence 591. Following a supported outcome that is admitted, durably receipted, and recovered, the test changes the planner's observed serving identity from model v1 to model v2. The same retained support no longer selects the goal: planning reports `epistemic_applicability_unresolved`, produces no work plan, and invokes neither execution nor a model. The fixture then restores the matching identity to continue checking the adverse outcome path.

Candidate `e19b4b354b29dbf7ba196a0de10b900ad3fe4c16`, tree `00c71c09576ee3f070cce3aaf59f7088ba5b8993`, was based on sequence 591 main `2746bf3a2efd5bf4ca89fe89cc5df95bce368727`. CI run 39849928877 passed full self-check, the integrated resource-to-cognition lifecycle, and exact canonical planning and execution-separation acceptance. Required Quality Gate 39849928629 passed strict Administrator audits, exact acceptance binding, audit immutability, hosted finalization, and the separate metadata guard. Gradient 39849928814, Lint Benchmark 39849928820, Release 39849928897, Docker 39849928819, Codex CI 39849928662, and Invariant Tests 39849928852 passed; all eight exact-candidate workflows were green.

PR #2641 merged normally as `02dae1f1322dc837a10fdc049901c29faa3c32d8`. Candidate-to-merge comparison reported zero changed files, retaining tree `00c71c09576ee3f070cce3aaf59f7088ba5b8993`. This is a deterministic fixture regression only; no model invocation, inference, or production transition occurred.

Sequence: 592 (verified source integration)
