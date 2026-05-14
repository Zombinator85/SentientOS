from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from scripts import build_reviewer_proof_bundle as script
from sentientos.reviewer_proof_bundle import BUNDLE_FILE_NAMES, validate_reviewer_proof_bundle_manifest

pytestmark = pytest.mark.no_legacy_skip


def _run_main(args: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = script.main(args)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, stdout.getvalue(), stderr.getvalue()


def test_requires_output_dir() -> None:
    code, _stdout, stderr = _run_main([])
    assert code != 0
    assert "output-dir" in stderr


def test_refuses_empty_root_and_file_output_dir(tmp_path: Path) -> None:
    code, _stdout, stderr = _run_main(["--output-dir", "/"])
    assert code != 0
    assert "filesystem root" in stderr
    file_path = tmp_path / "file.txt"
    file_path.write_text("not a directory", encoding="utf-8")
    code, _stdout, stderr = _run_main(["--output-dir", str(file_path)])
    assert code != 0
    assert "directory" in stderr


def test_writes_expected_files_and_manifest_validates(tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    code, stdout, stderr = _run_main(["--output-dir", str(out)])
    assert code == 0, stderr
    assert "proof commands executed: 0" in stdout
    for relative in BUNDLE_FILE_NAMES.values():
        assert (out / relative).exists(), relative
    manifest = json.loads((out / "bundle_manifest.json").read_text(encoding="utf-8"))
    validation = validate_reviewer_proof_bundle_manifest(manifest)
    assert validation.ok, validation.findings
    assert all(record["executed"] is False for record in manifest["proof_command_records"])
    assert all(record["status"] == "proof_command_not_run" for record in manifest["proof_command_records"])


def test_summary_prints_compact_summary(tmp_path: Path) -> None:
    code, stdout, stderr = _run_main(["--output-dir", str(tmp_path / "bundle"), "--summary"])
    assert code == 0, stderr
    assert "SentientOS Reviewer First-Run Proof Bundle" in stdout
    assert "metadata only: true" in stdout
    assert "fake/sample telemetry by default: true" in stdout


def test_existing_files_require_force_and_force_overwrites_only_bundle_files(tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    code, _stdout, stderr = _run_main(["--output-dir", str(out)])
    assert code == 0, stderr
    sentinel = out / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    code, _stdout, stderr = _run_main(["--output-dir", str(out)])
    assert code != 0
    assert "--force" in stderr
    (out / "trace.summary.txt").write_text("changed", encoding="utf-8")
    code, _stdout, stderr = _run_main(["--output-dir", str(out), "--force"])
    assert code == 0, stderr
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert "changed" not in (out / "trace.summary.txt").read_text(encoding="utf-8")


def test_default_does_not_run_live_collection_network_provider_or_prompt(tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    code, _stdout, stderr = _run_main(["--output-dir", str(out)])
    assert code == 0, stderr
    manifest = json.loads((out / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert manifest["live_host_collection_performed"] is False
    assert manifest["live_authorization_granted"] is False
    assert manifest["effect_performed"] is False
    assert manifest["host_mutation_performed"] is False
    assert manifest["network_performed"] is False
    assert manifest["provider_invocation_performed"] is False
    assert manifest["prompt_assembly_performed"] is False


def test_manifest_only_writes_only_manifest(tmp_path: Path) -> None:
    out = tmp_path / "bundle"
    code, _stdout, stderr = _run_main(["--output-dir", str(out), "--manifest-only"])
    assert code == 0, stderr
    assert (out / "bundle_manifest.json").exists()
    assert not (out / "trace.json").exists()


def test_verify_is_explicitly_unsupported(tmp_path: Path) -> None:
    code, _stdout, stderr = _run_main(["--output-dir", str(tmp_path / "bundle"), "--verify"])
    assert code == 2
    assert "not implemented" in stderr
