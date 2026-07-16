# Genesis reviewed candidate adoption custody

SentientOS now separates Genesis proposal evaluation from effect-capable adoption.
A bounded signal batch and Genesis need may produce optional governed model advice
and one canonical `GenesisCandidateEvaluation`; that evaluation can be sealed as a
data-only reviewed candidate and review packet. The packet grants no admission,
execution, lineage integration, adoption, Git authority, repository-source
mutation, model authority, or sentientosd automation.

The custody chain is:

1. `ReviewedGenesisCandidate` binds candidate/proposal/spec identity, normalized
   need, blueprint semantics, proposed spec, original spec digest, deltas, signal
   batch digest, evaluation digest, router scorecard digest, stage-A/stage-B
   evidence digests, sandbox digest, proof-budget digest, and optional advice
   lineage.
2. `GenesisCandidateReviewPacket` seals the exact reviewed candidate and
   successful evaluation evidence for a bounded lifetime with explicit
   no-authority/no-effect posture.
3. `GenesisCandidateReviewDecision` records an explicit operator disposition
   (`approve`, `reject`, or `defer`). Approval only makes the packet eligible to
   request control-plane admission.
4. `GenesisReviewedAdoptionPlan` binds the exact packet, decision, candidate,
   target labels, expected state, two mutation actions, rollback strategy, and an
   idempotency key.
5. `GenesisReviewedAdoptionCoordinator` obtains separate lineage and
   `AuthorityClass.PROPOSAL_ADOPTION` admissions before any write, then writes
   bounded runtime-state artifacts for the exact reviewed candidate only.
6. `GenesisReviewedAdoptionReceipt` or
   `GenesisReviewedAdoptionRollbackReceipt` records the complete attempt.

Adoption does not rescan telemetry/vows, draft candidates, invoke a model,
request advice, rerun stage A/B, reroute, reselect proof budget, rerun sandbox,
substitute equivalent candidates, infer approval from proposal readiness, infer
admission from approval, infer execution from admission, mutate repository
source, invoke Git, or run automatically from `sentientosd`.

World-State records represent review packets, decisions, plans, execution
attempts, rollbacks, and completed adoptions as separate lifecycle stages. A
review approval, admission, lineage record, or receipt without validated target
state is not treated as completed adoption.
