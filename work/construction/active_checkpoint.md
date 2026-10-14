# Active construction checkpoint

Sequence 217 makes persisted work-plan and work-run identities write once. Exact retries do not rewrite bytes or add duplicate pulse entries; conflicting content under an existing identity fails closed. This preserves completed outcome custody across replay. Partial task execution still does not have a restart journal.

Latest source commit: 78709ab27191effcfeae8022217e3dcb329fd203
Latest source tree: 37fedbfc158a3bd4fed472ed1cd8233c9646651c
Latest segment: work/construction/segments/0217-write-once-work-plan-custody.md
Evidence: work/construction/evidence/0217-write-once-work-plan-custody.json
Sequence: 217

Validation: 19 work-plan parsing/persistence and goal executor tests passed. Changed modules compiled and diff check passed.

Next: inspect the orchestrator's interruption window between task effect and final work-run persistence. Add only a bounded journal mechanism if existing owner contracts can distinguish attempted, completed, and unknown steps without replaying effects; ensure blocked dependencies do not consume independent authorized work.
