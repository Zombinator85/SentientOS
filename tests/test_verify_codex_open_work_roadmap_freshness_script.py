from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from scripts.verify_codex_open_work_roadmap_freshness import main
from tests.test_codex_open_work_roadmap_freshness_verifier import valid_roadmap


def test_missing_roadmap_exits_2(tmp_path: Path) -> None:
    assert main(["--roadmap-path", str(tmp_path / "missing.md")]) == 2


def test_empty_roadmap_exits_2(tmp_path: Path) -> None:
    roadmap = tmp_path / "empty.md"
    roadmap.write_text("", encoding="utf-8")
    assert main(["--roadmap-path", str(roadmap)]) == 2


def test_cli_writes_deterministic_json_and_markdown_outputs(tmp_path: Path) -> None:
    roadmap = tmp_path / "roadmap.md"
    roadmap.write_text(valid_roadmap(), encoding="utf-8")
    output = tmp_path / "report.json"
    markdown = tmp_path / "report.md"

    assert main(["--roadmap-path", str(roadmap), "--output", str(output), "--markdown-output", str(markdown), "--summary"]) == 0
    first_json = output.read_text(encoding="utf-8")
    first_md = markdown.read_text(encoding="utf-8")
    assert main(["--roadmap-path", str(roadmap), "--output", str(output), "--markdown-output", str(markdown)]) == 0
    assert output.read_text(encoding="utf-8") == first_json
    assert markdown.read_text(encoding="utf-8") == first_md
    payload = json.loads(first_json)
    assert payload["verification_status"] == "codex_open_work_roadmap_freshness_verified"


def test_cli_returns_1_for_successful_verification_with_violations(tmp_path: Path) -> None:
    roadmap = tmp_path / "roadmap.md"
    roadmap.write_text(valid_roadmap().replace("PR #1898", "PR missing"), encoding="utf-8")
    assert main(["--roadmap-path", str(roadmap)]) == 1


def test_unwritable_output_exits_2(tmp_path: Path) -> None:
    roadmap = tmp_path / "roadmap.md"
    roadmap.write_text(valid_roadmap(), encoding="utf-8")
    output_dir = tmp_path / "dir.json"
    output_dir.mkdir()
    assert main(["--roadmap-path", str(roadmap), "--output", str(output_dir)]) == 2
