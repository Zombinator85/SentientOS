# Embodiment Completion Masterplan (Post-Phase 50)

## Current implemented layers
- Phase 41: legacy perception quarantine + `sentientos.perception_api`.
- Phase 42: pulse telemetry bridge.
- Phase 43: `sentientos.embodiment_fusion` deterministic bounded snapshots.
- Phase 44: `sentientos.embodiment_ingress` non-authoritative ingress candidates.
- Phase 45/46: ingress-gated mic/feedback and screen/vision/multimodal retention paths.
- Phase 47: `sentientos.embodiment_gate_policy` shared policy.
- Phase 48: `sentientos.embodiment_proposals` append-only proposal queue.
- Phase 49: `sentientos.embodiment_proposal_diagnostic` visibility.
- Phase 50: `sentientos.embodiment_proposal_review` append-only review receipts and derived state.

## Intended full ladder
SENSE → FUSE → PRESSURE → GATE → PROPOSE → DIAGNOSE → REVIEW → HANDOFF → GOVERNANCE/ADMISSION BRIDGE → FULFILLMENT CANDIDATE → CONSENT/POLICY/ADMISSION CHECK → EFFECT RECEIPT → ACTUAL EFFECT.

## Boundary law
- Perception is telemetry only.
- Fusion is derived-only.
- Ingress is proposal-only.
- Review approval is not execution.
- Handoff is not admission.
- Governance bridge is not fulfillment.
- Fulfillment candidate is not effect.
- Effect requires consent/policy/admission and receipt.

## Remaining waves
### Wave A: reviewed proposal handoff/export candidates
Purpose: derive non-authoritative handoff candidates from latest approved reviews only.
Inputs: Phase 48 proposals + Phase 50 review receipts.
Outputs: handoff candidate records and summaries.
Modules: `sentientos.embodiment_proposal_handoff`.
Non-authoritative: no memory/action/admission/execution/control-plane mutation.
Tests: kind mapping, latest review wins, blocked outcomes filtered.
Out of scope: any admission/execution/fulfillment.

### Wave B: governance/admission bridge candidates
Purpose: derive governance-review candidates from eligible handoff candidates.
Inputs: Wave A handoff candidates.
Outputs: governance bridge candidates + blocked reasons.
Modules: `sentientos.embodiment_governance_bridge`.
Non-authoritative: no admission, no executor, no mutable state.
Tests: mapping, privacy/consent hold, unsupported kind handling.
Out of scope: task admission tokens, execution permissions.

### Wave C: fulfillment candidate + receipt surfaces
Purpose: normalize future executable intents and future receipts.
Inputs: governance-approved bridge outputs.
Outputs: fulfillment-candidate draft envelopes + non-effect receipts.
Modules likely: `sentientos.embodiment_fulfillment_candidates`, `sentientos.embodiment_fulfillment_receipts`.
Non-authoritative: candidate creation only.
Tests: envelope invariants, deterministic identity.
Out of scope: actual effect write.

### Wave D/E/F: governed ingress by effect class
- D memory ingress, E feedback/action ingress, F retention ingress.
- Purpose: execute only through consent/policy/admission contract.
- Inputs: fulfillment candidates + policy + consent + admission.
- Outputs: effect receipts + bounded effect APIs.
- Tests: denied admission, allowed admission, receipt requirement.
- Out of scope: bypass paths.

### Wave G: diagnostic/operator review consolidation
Purpose: unify proposal/review/handoff/bridge/fulfillment visibility.
Tests: additive schema stability and posture rollups.

### Wave H: default flip
Purpose: default gate mode to `proposal_only` from `compatibility_legacy` after coverage.
Tests: migration safety and compatibility.

### Wave I: quarantine burn-down
Purpose: deprecate legacy pathways with explicit migration gates.
Tests: no legacy writes to protected sinks.

## Concise implementation sequence
1) Build handoff derivation + tests.
2) Build governance bridge derivation + tests.
3) Add additive diagnostics and manifest boundaries.
4) Add fulfillment candidate surfaces.
5) Bind admission/consent/policy checks and effect receipts.
6) Flip defaults once green.
7) Remove legacy execution paths.

## Deferred risks
- Consent posture vocabulary may require stronger normalization.
- Privacy posture policy granularity may drift between modules.
- Future admission APIs must avoid accidental “candidate == token” coupling.
- Operator UX debt could hide blocked reasons if not consolidated in Wave G.
