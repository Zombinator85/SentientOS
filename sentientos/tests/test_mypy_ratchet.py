from __future__ import annotations

import json
from pathlib import Path

from scripts.mypy_ratchet import (
    CLUSTER_SUMMARY_PATH,
    DIGEST_PATH,
    RATCHET_STATUS_PATH,
    CANONICAL_BASELINE_PATH,
    MypyError,
    _canonical_repo_targets,
    _emit_typing_artifacts,
    _summary_report,
    build_baseline,
    main,
)


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


def test_canonical_repo_targets_filters_excludes(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "escrow").mkdir()
    (tmp_path / "scripts" / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "escrow" / "skip.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("demo\n", encoding="utf-8")
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True, text=True)
    policy = {"canonical_roots": ["."], "canonical_exclude_globs": ["escrow/*"]}
    targets = _canonical_repo_targets(tmp_path, policy)
    assert targets == ["scripts/ok.py"]


def test_emit_typing_artifacts_writes_expected_payloads(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    baseline = build_baseline([MypyError(path="sentientos/runtime/a.py", line=1, column=1, message="old", code="arg-type")])
    current = [
        MypyError(path="sentientos/runtime/a.py", line=1, column=1, message="old", code="arg-type"),
        MypyError(path="scripts/x.py", line=1, column=1, message="new", code="type-arg"),
    ]
    _emit_typing_artifacts(
        baseline_payload=baseline,
        current_errors=current,
        result={"status": "new_errors", "protected_scope": {"new_error_count": 0}},
        policy={"protected_patterns": ["sentientos/runtime/*.py"], "canonical_exclude_globs": []},
        checked_targets=["scripts/x.py", "sentientos/runtime/a.py"],
    )
    canonical = json.loads((tmp_path / CANONICAL_BASELINE_PATH).read_text(encoding="utf-8"))
    clusters = json.loads((tmp_path / CLUSTER_SUMMARY_PATH).read_text(encoding="utf-8"))
    ratchet = json.loads((tmp_path / RATCHET_STATUS_PATH).read_text(encoding="utf-8"))
    digest = json.loads((tmp_path / DIGEST_PATH).read_text(encoding="utf-8"))
    assert canonical["error_count"] == 2
    assert clusters["cluster_count"] >= 1
    assert ratchet["ratcheted_new_error_count"] == 1
    assert digest["delta_vs_baseline"] == 1
