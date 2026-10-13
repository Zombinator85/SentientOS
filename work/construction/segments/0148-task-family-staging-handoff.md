# Sequence 148 — Expose required task-family history in the operator staging path

Construction source base: 35cac696da1fc50c05fe316518df77a4ce6a952b, tree 7bd247ec0bde593c1ffda0c34b0755ee43a56b2f. The tested source increment is c506037c8bc58ae79d07b71836f9b08643d23fc8, tree 3c8b510f9f68288b34eb197fe8c66e8f228addb9; the code commit was published by expected-HEAD compare-and-swap and its branch, tree, and changed blobs were independently read back.

The controlled task-family acquisition/transfer path was already present in the owners. The supported stage API could require an exact family-backed admitted record, but the documented operator CLI could only stage the legacy general-history request. That interface mismatch could leave a real operator with valid but unrelated history.

Added `--task-family-id` and `--require-task-family-history` to the staging command. Required-family mode now passes through the same task schema and read-only writeback/tick/receipt preflight already used by the owner; absence of the flag preserves legacy behavior. A family label is explicitly only operator-declared relevance metadata, not proof of source truth, correctness, or learning. The operator procedure now shows how to require the exact family.

The family acquisition → normal admitted writeback → history-present/withheld/restored transfer → subsequent World-State feedback → continued transfer path was exercised with deterministic fixture invokers. The adverse incorrect-experience case remains adverse; the progression test verifies restart inspection performs no writes or inference replay. The exact four focused nodes passed on the tested source. These are fixture composition and instrumentation results, not actual local-model behavior or performance improvement.

Changed Python compiled. No typing, hosted CI, external host, or production verification was run. This construction increment is unverified for production.

Next: make the read-only host doctor report whether the selected task family has exact admitted source evidence before an operator stages the request; then proceed toward an actual task/outcome source and a user-host run only when its existing source, model, and serving gates are independently present.
