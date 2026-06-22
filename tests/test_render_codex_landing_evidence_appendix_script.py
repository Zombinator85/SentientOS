from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

TITLE = "[codex:landing] render Codex landing evidence appendix"


def test_cli_writes_markdown_json_sidecar_and_prints_compact_summary(tmp_path: Path) -> None:
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"evidence_index_id": "idx", "artifact_count": 0, "artifact_roles_present": [], "artifact_roles_missing": [], "aggregate_hints": {}, "artifacts": []}), encoding="utf-8")
    output = tmp_path / "appendix.md"
    sidecar = tmp_path / "appendix.json"
    result = subprocess.run(
        [sys.executable, "scripts/render_codex_landing_evidence_appendix.py", "--title", TITLE, "--intended-commit-title", TITLE, "--evidence-index-json", str(index), "--output", str(output), "--json-output", str(sidecar), "--summary"],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "# Codex Landing Evidence Appendix" in output.read_text(encoding="utf-8")
    assert json.loads(sidecar.read_text(encoding="utf-8"))["appendix_is_non_authoritative"] is True
    assert json.loads(result.stdout) == {"appendix_is_non_authoritative": True, "doctor_report_provided": False, "evidence_index_provided": True, "doctrine_map_provided": False, "doctrine_trait_count": 0, "doctrine_rail_mapping_count": 0, "output": str(output)}


def test_cli_failure_returns_exit_code_2_with_useful_message(tmp_path: Path) -> None:
    output = tmp_path / "appendix.md"
    result = subprocess.run(
        [sys.executable, "scripts/render_codex_landing_evidence_appendix.py", "--title", TITLE, "--intended-commit-title", TITLE, "--evidence-index-json", str(tmp_path / "missing.json"), "--output", str(output)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "codex_landing_evidence_appendix_error: evidence_index_json_missing" in result.stderr
    assert not output.exists()


def test_cli_accepts_doctrine_map_json_and_summary_mentions_intake(tmp_path: Path) -> None:
    doctrine = tmp_path / "doctrine.json"
    doctrine.write_text(json.dumps({"doctrine_map_id": "d", "metadata_only": True, "doctrine_only": True, "not_model_training": True, "not_reinforcement_learning": True, "trait_catalog": {"t": "definition"}, "rail_mappings": [{"rail_id": "r", "rail_name": "Rail", "enforced_traits": ["t"], "reviewer_summary": "summary"}], "trait_to_rails_index": {"t": ["r"]}, "non_authority_posture": {"doctrine_map_does_not_decide_readiness": True, "doctrine_map_does_not_authorize_commit": True, "doctrine_map_does_not_authorize_pr_creation": True, "doctrine_map_does_not_train_or_modify_models": True}}), encoding="utf-8")
    output = tmp_path / "appendix.md"
    sidecar = tmp_path / "appendix.json"
    result = subprocess.run([sys.executable, "scripts/render_codex_landing_evidence_appendix.py", "--title", TITLE, "--intended-commit-title", TITLE, "--doctrine-map-json", str(doctrine), "--output", str(output), "--json-output", str(sidecar), "--summary"], check=False, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "## Beneficial Trait Doctrine" in output.read_text(encoding="utf-8")
    assert json.loads(sidecar.read_text(encoding="utf-8"))["doctrine_map_json_path"] == str(doctrine)
    assert json.loads(result.stdout)["doctrine_map_provided"] is True


def test_cli_doctrine_json_failure_returns_exit_code_2_with_useful_message(tmp_path: Path) -> None:
    output = tmp_path / "appendix.md"
    result = subprocess.run([sys.executable, "scripts/render_codex_landing_evidence_appendix.py", "--title", TITLE, "--intended-commit-title", TITLE, "--doctrine-map-json", str(tmp_path / "missing_doctrine.json"), "--output", str(output)], check=False, text=True, capture_output=True)
    assert result.returncode == 2
    assert "codex_landing_evidence_appendix_error: doctrine_map_json_missing" in result.stderr
    assert not output.exists()
