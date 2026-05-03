# Phase 45 ExecPlan: Ingress-Gated Legacy Memory/Action Remediation

## 1) Current Phase-44 ingress state
Phase 44 established `sentientos.embodiment_ingress` as a non-authoritative proposal/receipt layer over embodiment fusion snapshots. It classifies pressure and emits hold/review postures but does not perform effects.

## 2) Direct memory/action paths inspected
- `mic_bridge.py`: direct `append_memory(...)` on recognized transcript.
- `feedback.py`: direct invocation of configured action callbacks in `FeedbackManager.process(...)`.
- Supporting paths: `sentientos/embodiment_ingress.py`, `sentientos/perception_api.py`, `sentientos/embodiment_fusion.py`.

## 3) Selected paths for gating
- Mic memory append path (high-risk mutable side effect).
- Feedback action trigger path (high-risk external side effect).

## 4) Compatibility strategy
Introduce explicit ingress gate mode with defaults preserving behavior:
- `proposal_only`: evaluate ingress + emit transition receipt; block direct side effects.
- `compatibility_legacy` (default): evaluate ingress + emit transition receipt; preserve direct side effects.
- Unsupported/other values naturally behave as non-legacy allow=false.

## 5) Transitional fallback behavior
Fallback remains explicit and visible:
- Receipts include `ingress_gate_mode`, `legacy_direct_effect`, `legacy_direct_effect_preserved`, `transition_state`.
- Module markers advertise gated-but-not-yet-fully-migrated state.

## 6) Tests to add/update
- Add `tests/test_phase45_ingress_gated_effects.py`:
  - mic proposal_only blocks memory append.
  - mic compatibility_legacy preserves memory append.
  - feedback proposal_only blocks action callback.
  - feedback compatibility_legacy preserves action callback.
  - ingress remains non-authoritative.
- Update architecture test coverage for gate marker visibility + known-violation visibility.

## 7) Deferred risks and why
- Other legacy direct JSONL writes remain in quarantined modules outside Phase 45 scope.
- Full admission/authorization replacement for legacy side effects is deferred to later phases to avoid orchestration and runtime semantic changes in this pass.
