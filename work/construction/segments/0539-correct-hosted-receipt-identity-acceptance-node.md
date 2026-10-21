# Sequence 539 — correct the hosted receipt-identity acceptance node

The first hosted source-validation attempt for sequence 538 correctly blocked acceptance. Its focused test included a parameterized test function, so pytest recorded parameter-suffixed node IDs while the task-acceptance manifest required the unsuffixed node. The cases themselves passed, but the exact source-bound acceptance node was not selected; the gate returned `task_acceptance_blocked`. The correction keeps one stable pytest node and exercises missing, malformed, and arbitrary recomputed receipt IDs in a loop. The acceptance manifest and hosted workflow contract continue to name that exact node.

After the correction, the full production-trial receipt and synthetic rehearsal tests passed locally (23 pytest nodes, covering the same 25 cases), targeted Mypy comparison showed the same 50 existing error signatures as the prior candidate and zero new signatures, and compilation, YAML parsing, and diff checks passed. The correction candidate's hosted CI and privileged Quality Gate are pending.

The sequence 538 implementation remains recorded in its original append-only segment/evidence snapshot. This segment records the test-node correction without rewriting that history. Its initial hosted CI run failed only at the acceptance verifier because of the node-ID mismatch; no behavior test failed.

Verified main: `500fd87c0d807f9ef2128902c166d04c3203f8fc`, tree `7bc937225377b689657cd52df96cbb604ccc2639`
Correction candidate: `d506514e0f655fdf3dd21faa16cd9fbf2695e963`, tree `e0fe12b7375584f38ce25f411d688425a3715dfe`
Initial source candidate: `abcb6ccd7b81d15c6ab3c69fb6c0fedeeacd4b5b`, tree `343687128774739c699b7ed2a2fb22c44c6c58f7`
Latest construction segment: `work/construction/segments/0539-correct-hosted-receipt-identity-acceptance-node.md`
Sequence: 539 (corrected candidate pending hosted verification)

No production transition, activation, serving, inference, or writeback was performed.
