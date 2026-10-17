# Sequence 330: bind the workflow continuation contract

## Hosted failure

The Required Quality Gate at candidate `b546146274091e5dcfdad9b903cf74971d0166bb`, run `39076111681`, passed strict Administrator audit, import-inertness, and pytest-bootstrap phases. Its call-phase shell then exited 127 because the final positive-recovery node lacked a trailing continuation, so the adverse same-generation test path was interpreted as a command. The workflow's existing contract test already checked continuation on every selected node except the last, but that contract itself was not part of the exact acceptance selection.

## Repair

Sequence 330 adds the missing continuation, includes `test_required_quality_gate_runs_exact_nodes_after_import_smoke` in the required call phase, and updates the exact required-node count from 25 to 26. Coverage is expanded; no test was removed or weakened. The next hosted run must execute the positive recovery, adverse same-generation rejection, and the workflow contract test before acceptance binding and privileged finalization can proceed.

## Verification boundary

The failure is tied to the exact candidate SHA and was not counted as passing validation. The strict audit passed, but acceptance binding and the PR landing finalizer were skipped after shell failure. Compilation and diff checks are run for this repair; exact hosted call-phase execution, finalization, and all required checks remain pending.

## Provenance

This increment follows sequence 329 from candidate commit `b546146274091e5dcfdad9b903cf74971d0166bb`, tree `913c5759f0a04339c5db4a7a9db5ff7142a982ec`. Sequence 286 provenance loss and the stale sequence-178 workspace remain preserved.
