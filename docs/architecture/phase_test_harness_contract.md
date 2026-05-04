# Phase Test Harness Contract

## Purpose
Phase-focused suites (`tests/test_phase*.py`) are product hardening tests, not legacy quarantine candidates.

## Contract
- New `tests/test_phase*.py` files must run under the standard harness by default.
- Central policy exemption prevents phase suites from being auto-classified as legacy.
- Individual test-level skips are allowed, but skip reasons must be explicit.
- Fully skipped phase suites are forbidden unless they include an explicit, searchable module-level skip reason and approval context.

## Implementation Notes
- Legacy quarantine remains active for non-phase tests.
- `pytest.mark.no_legacy_skip` remains valid for explicitness, but phase suites no longer depend on author memory to avoid quarantine.
- Contract enforcement meta-tests live in `tests/test_phase_test_harness_contract.py`.

## Reviewer Checklist for New Phase Files
1. File name matches `tests/test_phase*.py`.
2. Contains real `test_*` coverage (not placeholders).
3. Any skips include clear reason text.
4. If module-level skipped, reason is explicit and documented in review notes.
