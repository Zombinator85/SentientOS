from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from scripts.build_codex_beneficial_trait_doctrine import main


def test_cli_writes_json_and_prints_compact_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "codex_beneficial_trait_doctrine_map.json"
    assert main(["--output", str(output), "--summary"]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    summary = json.loads(capsys.readouterr().out)
    assert payload["metadata_only"] is True
    assert payload["doctrine_only"] is True
    assert summary["output"] == str(output)
    assert summary["metadata_only"] is True
    assert summary["trait_count"] >= 15
    assert summary["rail_mapping_count"] >= 10


def test_cli_writes_markdown_when_requested(tmp_path: Path) -> None:
    output = tmp_path / "codex_beneficial_trait_doctrine_map.json"
    markdown_output = tmp_path / "codex_beneficial_trait_doctrine_map.md"
    assert main(["--output", str(output), "--markdown-output", str(markdown_output)]) == 0
    markdown = markdown_output.read_text(encoding="utf-8")
    assert markdown.startswith("# Codex Beneficial Trait Doctrine Map")
    assert "## Non-authority posture" in markdown
    assert "not model training" in markdown
