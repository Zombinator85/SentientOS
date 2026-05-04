# Phase 60 ExecPlan: Phase-Focused Test Harness Anti-Skip Contract

## 1) Current legacy skip policy behavior
- `tests/conftest.py::pytest_collection_modifyitems` labels tests as `legacy` and skips them by default unless `-m legacy` is active.
- The skip decision is delegated to `tests/legacy_policy.py::is_legacy_candidate(...)`.
- Current opt-outs rely on:
  - allowlisted module names in `tests/conftest.py` (`allowed_modules`), or
  - explicit `pytest.mark.no_legacy_skip` markers.
- Net effect: newly introduced files can be silently quarantined if authors forget markers/allowlist updates.

## 2) Recent accidental skip incidents
- Phase 45/46 focused ingress embodiment tests were added and later unskipped.
- Phase 48/49/50 focused embodied proposal/review tests were added and later unskipped in follow-up hardening.
- Phase 56/57/58 focused truth tests were added and later unskipped in Phase 59.
- Pattern: `tests/test_phase*.py` files are phase-focused but vulnerable to legacy quarantine-by-default behavior.

## 3) Target phase-test contract
- Files matching `tests/test_phase*.py` are **phase-focused** and not legacy by default.
- They must either:
  1. run under standard harness by default, or
  2. declare an explicit module-level skip with a searchable, documented reason.
- Individual skipped tests are permitted with explicit reason text.
- Fully skipped phase modules are forbidden unless explicitly and intentionally approved via module-level skip reason.

## 4) Changes to conftest/marker policy
- Apply a **central policy fix** in `tests/legacy_policy.py`:
  - Exempt `tests/test_phase*.py` from legacy candidacy by default.
- Preserve existing legacy semantics for non-phase tests.
- Keep `no_legacy_skip` marker support unchanged (still valid and explicit).

## 5) Meta-tests to add
- Add `tests/test_phase_test_harness_contract.py` to statically enforce:
  - every `tests/test_phase*.py` module either has runnable tests or explicit module-level skip;
  - module-level skip reasons (when present) are explicit and searchable;
  - phase modules are not legacy candidates under `is_legacy_candidate(...)` defaults;
  - representative Phase 45–59 modules satisfy contract.

## 6) Compatibility strategy for intentionally skipped legacy tests
- No changes to existing legacy-only test behavior.
- Existing non-phase suites continue to rely on allowlist/markers and legacy quarantine semantics.
- Intentional skip behavior for phase suites remains possible through explicit module-level skip declarations.

## 7) Risks and deferred cleanup
- Risk: `test_phase` naming convention drift (e.g., alternate filenames) could bypass contract; deferred: add naming lint if repo starts using alternates.
- Risk: static checks may miss dynamic skip behavior inside fixtures; mitigated by constraining module-level policy and central legacy exemption.
- Deferred cleanup: reduce `allowed_modules` sprawl in `tests/conftest.py` via separate policy normalization pass (out of scope).
