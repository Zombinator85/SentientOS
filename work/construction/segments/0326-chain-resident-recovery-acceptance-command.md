# Sequence 326: keep exact acceptance nodes in one hosted test invocation

## Source and failure

This increment starts from sequence 325 candidate `3ccc031c55c7889d5ad210186faf30d0bbd08057`, tree `7de5d374c1d54861c5959011a32da35f94db2cf7`.

Hosted Quality Gate run `39075370096` passed strict audit execution, import inertness, and pytest-bootstrap checks, then failed when executing the newly extended acceptance command. The two PID-recovery node IDs were on separate shell lines because the prior line lacked a continuation backslash. Bash attempted to execute the first node ID as a command and returned exit code 127. Exact acceptance verification and privileged landing finalization were consequently skipped. This is a source-caused verification failure, not a passing test or environmental failure.

## Repair

The node selection now continues the shell command through both recovery test IDs. The workflow contract test checks that every selected-node line except the final one ends with a continuation. This keeps the command grouping under the existing `scripts.run_tests` airlock; no alternate pytest invocation or privilege is introduced.

## Verification boundary

This repair has passed local compilation for the workflow contract test and `git diff --check`. A fresh hosted Quality Gate must execute all 25 selected call-phase nodes, including both recovery tests, and pass its Administrator finalizer. The remaining required CI, Docker, documentation, invariant, and lint checks must also pass for this exact head before landing.

No production Federation change, model transition, provider invocation, or authority expansion is claimed. Sequence 286 provenance loss and the stale sequence-178 workspace remain preserved.
