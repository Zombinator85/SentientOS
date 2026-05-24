from __future__ import annotations

import json

from scripts import codex_pr_validation_evidence as cli


def test_verify_fails_without_matrix(capsys) -> None:  # type: ignore[no-untyped-def]
    rc = cli.main(["verify", "--title", "[codex:developer] ok", "--body", "local tests only"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert "matrix_evidence_missing" in payload["findings"]


def test_build_from_matrix(capsys) -> None:  # type: ignore[no-untyped-def]
    matrix = json.dumps({"status": "passed", "required_failure_count": 0, "results": [{"label": "targeted_mypy", "exit_code": 0}, {"label": "mypy_baseline", "exit_code": 0}, {"label": "docs_build", "exit_code": 0}, {"label": "prompt_boundaries", "exit_code": 0}, {"label": "strict_audits", "exit_code": 0}, {"label": "audit_immutability", "exit_code": 0}, {"label": "docs_check_deps", "exit_code": 0}]})
    rc = cli.main(["build", "--matrix-json", matrix])
    assert rc == 0
    assert "Matrix runner --output result/path" in capsys.readouterr().out
