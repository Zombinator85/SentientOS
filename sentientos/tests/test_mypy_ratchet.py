from __future__ import annotations

from scripts.mypy_ratchet import MypyError, build_baseline


def test_baseline_compare_unchanged_passes() -> None:
    baseline_errors = [MypyError(path="sentientos/a.py", line=10, column=1, message='Incompatible types in assignment (expression has type "str", variable has type "int")', code="assignment")]
    baseline = build_baseline(baseline_errors)
    baseline_signatures = {
        str(item.get("signature"))
        for rows in baseline["errors_by_module"].values()
        for item in rows
        if isinstance(item, dict)
    }
    current_signatures = {baseline_errors[0].signature()}
    assert current_signatures - baseline_signatures == set()


def test_baseline_compare_new_error_fails_count() -> None:
    baseline_errors = [MypyError(path="sentientos/a.py", line=10, column=1, message="one", code="assignment")]
    current_errors = baseline_errors + [MypyError(path="sentientos/b.py", line=2, column=1, message="two", code="arg-type")]

    baseline = build_baseline(baseline_errors)
    baseline_signatures = {
        str(item.get("signature"))
        for rows in baseline["errors_by_module"].values()
        for item in rows
        if isinstance(item, dict)
    }
    new = {error.signature() for error in current_errors} - baseline_signatures
    assert len(new) == 1
