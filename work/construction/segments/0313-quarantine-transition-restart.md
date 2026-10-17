# Sequence 313 — Quarantine daemon cognition after unresolved transition recovery

PR #2308 closed a process-restart gap in resident transition handling. A fresh daemon has no surviving process-local quiescence token; startup now consults the canonical transition journal and keeps resident cognition quarantined when composition or recovery is unresolved. It does not mint a replacement gate token, mutate the journal, replay a transition stage, or grant a new effect authority.

The accepted path is bound to `test_transition_quarantine_reads_canonical_journal_without_reconstructing_gate`. The source validation had one superseded attempt: the unrelated local-model subprocess test reported `chat_process_runtime_handoff_child_not_running` in attempt 1. Attempt 2 passed, as did source validation on the same candidate SHA and the exact-head PR checks. This transient failure remains recorded below.

PR #2308 merged normally to main as `79641a494f763e10de28f7f3ea67d51b2163fcfc`, tree `74f9afb946573ab7f240f5a3a2c54f998545ecf1`. Sequence 314 records the follow-up semantic-verifier edge on its successor main.

The optional `invite` workflow could not post its nonessential comment (403); it is not a required check and no additional write permission was granted. Sequence 286's nine known and one unidentified unrecoverable payloads remain unresolved. The stale sequence-178 workspace remains untouched.
