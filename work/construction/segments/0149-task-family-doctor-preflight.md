# Sequence 149 — Qualify preflight by exact task-family history

Base source: 63b70e27ba0059fc327de3d6d3bb8e66e42ad730, tree a7bdb7694bb649d615d10cd47d9561697183c30a. Tested source: d20cc8bafb162484f4e6d061e908b146ed4f6575, tree b1ec482c9da738f2ae4cc9b46f1c20b2932b9cdb, published by expected-HEAD CAS; branch, tree, and all changed blobs were independently read back.

The stage CLI now supports a required task-family history contract, so the host doctor could still report generic-history readiness while the exact request would be denied later. The doctor now accepts the same optional family identity and delegates selection to `inspect_checkpointed_history_record_refs`. Its report includes the exact matching admitted record IDs and digests. It reports `awaiting_matching_task_family_history` when valid unrelated history exists but no completed, receipt-bound record in the requested family is eligible. The operation is read-only and creates no staged request.

The end-to-end task-family acquisition/transfer owner test now checks both a matching family and a nonmatching family through the doctor and verifies the cognition-state bytes remain unchanged. Existing checks exercise normal writeback, history-present/withheld/restored delivery, subsequent feedback, adverse incorrect experience, multi-episode progression, and child-process result reconstruction.

Two focused owner tests passed and changed Python compiled. These paths use deterministic fixture inference/evaluator custody; they establish the operator preflight's evidence selection, not real-model acquisition or performance. Typing, hosted checks, model-host execution, and production verification were not run.

Next: continue source-backed task/outcome closure by reviewing the exact experiment score and source lineage exposed for later World-State interpretation; retain model-originated task answers as scored observations, not external events. Then proceed toward a real POSIX host run only when actual model custody, serving, and per-call admission are independently available.
