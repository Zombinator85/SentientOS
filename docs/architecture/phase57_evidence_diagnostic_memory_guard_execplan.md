# Phase 57 ExecPlan: Evidence Stability Diagnostic + Truth Memory-Ingress Guard

1. **Current Phase 56 truth spine state**
   - Phase 56 supplies append-only claim/evidence/stance/contradiction receipts with deterministic ids and non-authority invariants.
   - It detects no-new-evidence reversal, unsupported dilution, and unsupported source undermining but does not summarize posture or gate ingress.

2. **Existing diagnostics inspected**
   - `sentientos/scoped_lifecycle_diagnostic.py`
   - Existing embodiment ingress validators (`sentientos/embodiment_memory_ingress.py`)
   - Architecture manifest + architecture boundary tests.

3. **Diagnostic summary shape**
   - Add `sentientos/truth/evidence_diagnostic.py` producing a read-only summary: counts, active stance, contradiction classes, posture classification, and explicit non-authority metadata.

4. **Memory-ingress guard shape**
   - Add `sentientos/truth/memory_ingress_guard.py` producing per-claim guard records and a summary; outcome vocabulary explicitly includes blocked/needs-review/validated-for-future-memory (validation-only).

5. **Relationship to embodiment memory ingress validation**
   - Truth guard is independent and additive. It does not call or alter embodiment memory write paths.
   - Embodiment memory ingress semantics remain unchanged.

6. **Inputs consumed**
   - Claim receipts, evidence receipts, stance receipts, contradiction receipts.
   - No retrieval or external data acquisition.

7. **Validation rules for memory eligibility**
   - Missing evidence blocks source-backed claims.
   - Underconstrained/plausible/unknown/blocked statuses block active memory ingress.
   - Blocking contradiction severity/adjudication blocks or holds.
   - Specific contradiction types (`no_new_evidence_reversal`, `unsupported_dilution`, `unsupported_source_undermining`, `quote_fidelity_failure`) block.
   - Retracted/superseded/contradicted statuses block active memory ingress.
   - Active stance must match claim or preserve prior claim via `policy_block_but_preserve`.
   - Supported statuses with evidence and no blocking contradictions validate for future memory path.

8. **Why guard validation is not memory write**
   - Guard records include explicit invariants: `guard_is_not_memory_write`, `validation_is_not_memory_write`, `does_not_write_memory`, `decision_power: none`.
   - No mutation APIs are imported or invoked.

9. **Tests to add/update**
   - Add focused phase57 tests for diagnostic posture/counts/non-authority flags, guard outcomes/rules, policy preserve handling, and caller immutability.
   - Update architecture boundaries tests for import isolation + manifest invariants for new truth layers.
   - Validate scoped lifecycle diagnostic additive field behavior.

10. **Deferred waves**
   - Research response gate.
   - Multi-turn adversarial harness.
   - Response-time stance consistency middleware.
   - Actual memory/effect integration with governed write pathways.
