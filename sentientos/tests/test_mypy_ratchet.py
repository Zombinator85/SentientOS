from __future__ import annotations

import json
from pathlib import Path

from scripts.mypy_ratchet import MypyError, _summary_report, build_baseline, main


def test_baseline_compare_unchanged_passes() -> None:
    baseline_errors = [MypyError(path="sentientos/a.py", line=10, column=1, message='Incompatible types in assignment (expression has type "str", variable has type "int")', code="assignment")]
    baseline = build_baseline(baseline_errors)
    baseline_signatures = {
        str(item.get("stable_signature"))
        for rows in baseline["errors_by_module"].values()
        for item in rows
        if isinstance(item, dict)
    }
    current_signatures = {baseline_errors[0].stable_signature()}
    assert current_signatures - baseline_signatures == set()


def test_baseline_compare_new_error_fails_count() -> None:
    baseline_errors = [MypyError(path="sentientos/a.py", line=10, column=1, message="one", code="assignment")]
    current_errors = baseline_errors + [MypyError(path="sentientos/b.py", line=2, column=1, message="two", code="arg-type")]

    baseline = build_baseline(baseline_errors)
    baseline_signatures = {
        str(item.get("stable_signature"))
        for rows in baseline["errors_by_module"].values()
        for item in rows
        if isinstance(item, dict)
    }
    new = {error.stable_signature() for error in current_errors} - baseline_signatures
    assert len(new) == 1


def test_summary_report_counts_protected_modules() -> None:
    baseline = {
        "error_count": 3,
        "errors_by_module": {
            "sentientos/runtime/core_loop.py": [{"path": "sentientos/runtime/core_loop.py", "message": "m", "code": "arg-type"}],
            "scripts/audit_immutability_verifier.py": [{"path": "scripts/audit_immutability_verifier.py", "message": "n", "code": "attr-defined"}],
            "sentientos/narrative/story.py": [{"path": "sentientos/narrative/story.py", "message": "x", "code": "misc"}],
        },
    }
    policy = {
        "protected_patterns": ["sentientos/runtime/*.py", "scripts/audit_*.py"],
        "strict_patterns": ["sentientos/runtime/*.py"],
    }
    report = _summary_report(baseline_payload=baseline, policy=policy)
    assert report["protected_module_count"] == 2
    assert report["strict_module_count"] == 1


def test_report_mode_emits_summary(tmp_path: Path, capsys) -> None:
    baseline_path = tmp_path / "baseline.json"
    policy_path = tmp_path / "policy.json"
    baseline_path.write_text(
        json.dumps(
            {
                "error_count": 1,
                "errors_by_module": {
                    "sentientos/runtime/core_loop.py": [
                        {
                            "path": "sentientos/runtime/core_loop.py",
                            "message": "oops",
                            "code": "arg-type",
                            "stable_signature": "sentientos/runtime/core_loop.py:arg-type:oops",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps({"protected_patterns": ["sentientos/runtime/*.py"], "strict_patterns": []}),
        encoding="utf-8",
    )
    rc = main(["--baseline", str(baseline_path), "--policy", str(policy_path), "--report"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 0
    assert payload["status"] == "ok"
    assert payload["report"]["protected_module_count"] == 1
