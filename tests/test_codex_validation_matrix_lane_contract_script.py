from __future__ import annotations

import json

from scripts import codex_validation_matrix_lane_contract as cli


def _write(tmp_path) -> str:  # type: ignore[no-untyped-def]
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"status": "passed", "required_failure_count": 0, "results": [{"label": "targeted_tests", "exit_code": 0}, {"label": "targeted_mypy", "exit_code": 0}, {"label": "mypy_baseline", "exit_code": 0}, {"label": "docs_check_deps", "exit_code": 0}, {"label": "docs_build", "exit_code": 0}, {"label": "prompt_boundaries", "exit_code": 0}, {"label": "strict_audits", "exit_code": 0}, {"label": "audit_immutability", "exit_code": 0}]}), encoding="utf-8")
    return str(p)


def test_list_lanes(capsys) -> None:  # type: ignore[no-untyped-def]
    assert cli.main(["list"]) == 0
    assert "targeted_mypy" in capsys.readouterr().out


def test_verify(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert cli.main(["verify", "--matrix-json-path", _write(tmp_path)]) == 0
    assert "codex_validation_matrix_lane_contract_ready" in capsys.readouterr().out
