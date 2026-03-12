from __future__ import annotations

import json
from pathlib import Path

from sentientos.formal_verification import run_formal_verification


def _copy_formal_tree(repo_root: Path, dst: Path) -> None:
    (dst / "formal/specs").mkdir(parents=True, exist_ok=True)
    (dst / "formal/models").mkdir(parents=True, exist_ok=True)
    for src in (repo_root / "formal/specs").glob("*"):
        if src.is_file():
            (dst / "formal/specs" / src.name).write_bytes(src.read_bytes())
    for src in (repo_root / "formal/models").glob("*.json"):
        (dst / "formal/models" / src.name).write_bytes(src.read_bytes())


def test_formal_check_generates_artifacts_and_manifest(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    _copy_formal_tree(repo_root, tmp_path)

    payload = run_formal_verification(tmp_path)
    assert payload["status"] == "passed"
    assert payload["spec_count"] == 4
    artifacts = payload["artifact_paths"]
    assert isinstance(artifacts, dict)

    summary = tmp_path / str(artifacts["summary"])
    manifest = tmp_path / str(artifacts["manifest"])
    assert summary.exists()
    assert manifest.exists()

    summary_payload = json.loads(summary.read_text(encoding="utf-8"))
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert summary_payload["status"] == "passed"
    assert summary_payload["run_digest"]
    assert sorted(manifest_payload["checked_files"]) == sorted(summary_payload["checked_spec_files"])


def test_formal_check_subset_is_deterministic(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    _copy_formal_tree(repo_root, tmp_path)

    a = run_formal_verification(tmp_path, selected_specs=["runtime_governor"])
    b = run_formal_verification(tmp_path, selected_specs=["runtime_governor"])

    assert a["status"] == "passed"
    assert b["status"] == "passed"
    assert a["run_digest"] == b["run_digest"]
    assert a["spec_count"] == 1
    assert b["spec_count"] == 1
