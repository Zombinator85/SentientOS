# Phase 58 ExecPlan: Truth Log-Fed Diagnostics + Stance-Consistency Preflight

1. **Current Phase 56/57 truth spine state**
   - Phase 56 provides append-only evidence/claim/stance/contradiction receipts plus transition and contradiction detection primitives.
   - Phase 57 adds read-only evidence stability diagnostics and validation-only truth memory ingress guard, but scoped lifecycle integration uses empty/default truth inputs.

2. **Existing ledger append/list APIs inspected**
   - `sentientos/truth/evidence_ledger.py`: append/list via `append_evidence_receipt`, `list_recent_evidence_receipts`.
   - `sentientos/truth/claim_ledger.py`: append/list via `append_claim_receipt`, `list_recent_claim_receipts`.
   - `sentientos/truth/stance_receipts.py`: receipt builders and transition/contradiction logic; add append/list helpers for stance + contradiction ledgers in this phase.

3. **Default log path strategy**
   - Use canonical truth log folder `logs/truth/` to match existing phase56 defaults.
   - Default paths:
     - `logs/truth/evidence_ledger.jsonl`
     - `logs/truth/claim_ledger.jsonl`
     - `logs/truth/stance_ledger.jsonl`
     - `logs/truth/contradiction_ledger.jsonl`
   - Allow path injection for deterministic hardware-free tests.

4. **Scoped lifecycle diagnostic integration plan**
   - Keep additive fields from phase57.
   - Attempt log-fed load in `sentientos/scoped_lifecycle_diagnostic.py`; if load issues occur, degrade safely to empty/default diagnostics and expose explicit load status/errors fields.

5. **Stance-consistency preflight shape**
   - New module `sentientos/truth/stance_preflight.py` with deterministic validation-only helpers:
     - `build_stance_preflight_record`
     - `validate_planned_claim_against_stance`
     - `classify_stance_preflight_outcome`
     - `stance_preflight_ref`
     - `summarize_stance_preflight_results`
   - Include required non-authority and non-generation flags.

6. **No-new-evidence / no-reversal enforcement**
   - Reuse `validate_stance_transition` and `detect_no_new_evidence_reversal`.
   - Block unsupported reversal/dilution/source-undermining/quote-fidelity-failure/silent-evidence-removal when unsupported by new evidence or explicit rationale.

7. **Relationship to future research response gate**
   - Phase 58 preflight is validation-only and does not generate responses.
   - Future live response gate will consume preflight outcomes but remains deferred.

8. **Tests to add/update**
   - New: `tests/test_phase58_truth_log_fed_preflight.py` covering log-fed load, safe degradation, malformed-line handling, scoped diagnostic integration, and preflight outcomes/boundaries.
   - Update architecture boundary tests for new module import purity and manifest invariants.

9. **Deferred waves**
   - Live research response gate.
   - Claim extraction from model text.
   - Retrieval/web integration.
   - Memory/effect integration.
