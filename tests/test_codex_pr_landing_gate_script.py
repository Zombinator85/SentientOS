from __future__ import annotations

import json
from pathlib import Path

from scripts import codex_pr_landing_gate as cli


def _matrix() -> str:
    return json.dumps({"status": "passed", "required_failure_count": 0, "results": [{"label": "targeted_tests", "exit_code": 0, "required": True}, {"label": "targeted_mypy", "exit_code": 0, "required": True}, {"label": "mypy_baseline", "exit_code": 0, "required": True}, {"label": "docs_check_deps", "exit_code": 0, "required": False}, {"label": "docs_build", "exit_code": 0, "required": True}, {"label": "prompt_boundaries", "exit_code": 0, "required": True}, {"label": "strict_audits", "exit_code": 0, "required": True}, {"label": "audit_immutability", "exit_code": 0, "required": True}]})


def test_gate_allows(capsys) -> None:  # type: ignore[no-untyped-def]
    rc = cli.main(["gate", "--title", "[codex:developer] ok", "--intended-commit-title", "[codex:developer] ok", "--matrix-json", _matrix()])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "pr_metadata_allowed"


def test_gate_accepts_matrix_json_path(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(_matrix(), encoding="utf-8")
    rc = cli.main(["gate", "--title", "[codex:developer] ok", "--intended-commit-title", "[codex:developer] ok", "--matrix-json-path", str(matrix_path)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "pr_metadata_allowed"


def test_gate_accepts_pathlike_matrix_json_compat(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(_matrix(), encoding="utf-8")
    rc = cli.main(["gate", "--title", "[codex:developer] ok", "--intended-commit-title", "[codex:developer] ok", "--matrix-json", str(matrix_path)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "pr_metadata_allowed"
