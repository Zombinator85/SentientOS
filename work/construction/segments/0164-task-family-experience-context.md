## 2026-10-13 checkpoint — deliver source-bound task examples through history context

- Continued from verified source commit 629805a99fdbdef5340eb2f96a3959720b0fd077 / tree 3dfabb4bbe6b7682c92f9ecc5c10d5a50ab3d188. Fresh continuation HEAD was ca78478f7032ceb390753bccebdb3b20573586fa / tree 22fcba424f8fc37ac7d4e540ec0df78a9147c34f.
- Source inspection showed task-family retrieval selected the correct admitted record, but the cognitive history packet sent only its free-form interpretation and record IDs. The structured, independently scored examples that justified task-family eligibility were not composed into the later prompt; a fixture could therefore appear to transfer from a preset narrative instead of the admitted source outcome.
- The existing history-packet builder now adds a small task-relevant experience projection only when the later task declares the same family. It validates the admitted fact/subject/source binding, safe salted task identity, history-present score digest/evaluator, and each bounded example's score and condition lineage. It includes the observed input/output and evaluator correctness, exact source/run/score IDs, and an explicit benchmark-only scope. It never includes private multiplier/offset parameters.
- This data goes only through the existing developmental-history treatment. The current World-State projection is unchanged; the withheld arm receives no history packet; the restored arm receives the same selected historical record. A different family gets no matching examples. Failed or missing lineage yields no task-example projection.
- The new integration case composes official staging, a deterministic task score, World-State, normal admitted developmental writeback, a reconstructed owner, and a second distinct held-out task. The fixture derives answers from the admitted examples: history-present 3/3, withheld 0/3, restored 3/3. This establishes fixture transfer composition, not real-model learning or a process-fresh restart.

Validation on the published source bytes:
- Compilation and trailing-whitespace checks passed for both changed Python files.
- Focused source-bound episode, family transfer, adverse-example, and progression tests: 4 passed.
- The episode's owner was reconstructed in-process and reused fixture receipt custody; a fresh-process second inference remains unverified and is next. Existing read-only child-process progression/report checks are separate and do not prove that new inference survived a fresh process.

Source commit: ca78478f7032ceb390753bccebdb3b20573586fa
Source tree: 22fcba424f8fc37ac7d4e540ec0df78a9147c34f
Changed blob identities are recorded in the accompanying evidence JSON. Construction remains unverified for production.

Next: run the second held-out episode from a fresh interpreter using only bounded durable record, admission, staged-request, and invocation-receipt custody. Reconstruct prior fixture receipt verification from serialized receipt evidence without inheriting the fake invoker object. Then audit missing/corrupted source bindings and currentness/contradiction controls.
