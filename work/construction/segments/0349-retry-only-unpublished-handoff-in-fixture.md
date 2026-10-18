# Sequence 349: mirror bounded handoff publication wait in the test child

## Failure diagnosis and correction

Post-merge CI on main `617fdad39833c05cf0e0a1784d46e59a73cfd5b3` exposed a single source-validation failure in `test_actual_adapter_handoff_binds_live_child_and_source_generation`: `chat_process_runtime_handoff_child_not_running`. The uploaded failure artifact showed that the synthetic child called `verify_current_chat_process_handoff` once, immediately after spawn, before its parent had necessarily published the immutable handoff. In contrast, the production child uses a bounded publication window and retries only `chat_process_handoff_unavailable`, then verifies the handoff lineage.

The test fixture now mirrors that exact five-second bounded retry and lineage check. Every other `ChatProcessGenerationError` still fails immediately; the parent must still publish a valid handoff, and the existing process/source-generation assertions remain. No production runtime behavior or authority changed.

## Local verification

On the exact source candidate, the focused startup, recovery, and process-generation integration suites passed 38 tests with one pre-existing legacy-marked test skipped. The formerly failing node passed 20 consecutive isolated invocations. `py_compile` and `git diff --check` passed. The full source-validation lane passed on the candidate after this correction.
