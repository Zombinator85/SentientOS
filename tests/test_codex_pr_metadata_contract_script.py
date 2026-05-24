from __future__ import annotations

import json

from scripts import codex_pr_metadata_contract as cli


def test_verify_summary_passes(capsys) -> None:  # type: ignore[no-untyped-def]
    body = """
## Full command matrix results\nok
## Matrix runner --summary result\nok
## Matrix runner --output result/path\nartifacts/x.json
## Targeted mypy result\nok
## Baseline result\nok
## Docs build result\nok
## Prompt-boundary result\nok
## Strict audit result\nok
## Immutability verifier result\nok
## Unresolved risks\nnone
"""
    rc = cli.main(["verify", "--title", "[codex:developer] ok", "--body", body, "--summary"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "codex_pr_metadata_contract_ready"


def test_build_outputs_required_sections(capsys) -> None:  # type: ignore[no-untyped-def]
    rollup = json.dumps(
        {
            "full_command_matrix_results": "a",
            "matrix_runner_summary_result": "b",
            "matrix_runner_output_result_path": "c",
            "targeted_mypy_result": "d",
            "baseline_result": "e",
            "docs_build_result": "f",
            "prompt_boundary_result": "g",
            "strict_audit_result": "h",
            "immutability_verifier_result": "i",
            "unresolved_risks": "j",
        }
    )
    assert cli.main(["build", "--rollup-json", rollup]) == 0
    out = capsys.readouterr().out
    assert "## Matrix runner --output result/path" in out
