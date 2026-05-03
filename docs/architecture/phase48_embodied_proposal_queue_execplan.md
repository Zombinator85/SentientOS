# Phase 48 ExecPlan: embodied ingress proposal queue and review surface

1. **Phase 47 gate state**: legacy perception modules already evaluate ingress receipts and gate side effects by `proposal_only` vs `compatibility_legacy` using `sentientos.embodiment_gate_policy` + `sentientos.embodiment_ingress`.
2. **Blocked paths**: mic memory append, feedback action callback, screen OCR retention write, vision emotion retention write, multimodal retention writes.
3. **Target surface**: add `sentientos.embodiment_proposals` as canonical append-only non-authoritative proposal ledger with deterministic IDs and pending-review status.
4. **Append-only/provenance strategy**: proposal records include ingress receipt refs, source refs, snapshot refs, correlation id, risk/consent/privacy posture, rationale; appends go through `sentientos.ledger_api.append_audit_record`.
5. **Boundary relationships**: embodiment_ingress remains classifier/receipt source, proposals consume ingress receipts only; no coupling to orchestration admission/execution (`task_admission`, `task_executor`) or control-plane mutation.
6. **Tests**: add phase48 focused tests for builder/append/list and all five legacy modules in `proposal_only`; keep compatibility behavior assertions; extend architecture boundary tests + manifest checks.
7. **Deferred risks**: compatibility mode still permits direct effects by design; no approval UI/admission wiring yet; proposal queue is review-only and intentionally non-authoritative.
