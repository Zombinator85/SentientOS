from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from scripts.emit_contract_manifest import emit_manifest

ROOT = Path(__file__).parents[1]


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def test_manifest_emits_required_bundle_from_another_working_directory(tmp_path: Path) -> None:
    contract_dir = tmp_path / "custody" / "contracts"
    _write_json(contract_dir / "contract_status.json", {"schema_version": 1, "status": "observed"})
    _write_json(contract_dir / "stability_doctrine.json", {"schema_version": 1, "audit_strict_status": "fail"})
    _write_json(contract_dir / "artifact_metadata.json", {"sha": "source-sha", "run_id": 17})
    _write_json(contract_dir / "ci_baseline.json", {"schema_version": 1, "passed": False})
    _write_json(contract_dir / "contract_manifest.json", {"stale": True})

    # Exercise the same module entrypoint used by CI with an explicit output
    # directory while the process cwd is unrelated to the repository.
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.emit_contract_manifest",
            "--contract-dir",
            str(contract_dir),
            "--git-sha",
            "source-sha",
            "--created-at",
            "2026-01-02T03:04:05Z",
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr

    manifest = json.loads((contract_dir / "contract_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["git_sha"] == "source-sha"
    assert manifest["created_at"] == "2026-01-02T03:04:05Z"
    assert manifest["required_files"] == [
        "stability_doctrine.json",
        "contract_status.json",
        "artifact_metadata.json",
        "contract_manifest.json",
    ]
    assert set(manifest["file_sha256"]) == {
        "stability_doctrine.json",
        "contract_status.json",
        "artifact_metadata.json",
        "ci_baseline.json",
    }
    assert "contract_manifest.json" not in manifest["file_sha256"]
    expected_bundle = "".join(
        f"{name}\n{digest}\n" for name, digest in sorted(manifest["file_sha256"].items())
    )
    assert manifest["bundle_sha256"] == hashlib.sha256(expected_bundle.encode()).hexdigest()


def test_manifest_fails_closed_when_required_input_is_missing(tmp_path: Path) -> None:
    contract_dir = tmp_path / "contracts"
    contract_dir.mkdir()
    _write_json(contract_dir / "contract_status.json", {"schema_version": 1})
    with pytest.raises(FileNotFoundError, match="stability_doctrine.json"):
        emit_manifest(contract_dir, git_sha="sha", created_at="time")
    assert not (contract_dir / "contract_manifest.json").exists()


def test_manifest_fails_closed_for_malformed_required_json(tmp_path: Path) -> None:
    contract_dir = tmp_path / "contracts"
    contract_dir.mkdir()
    (contract_dir / "contract_status.json").write_text("{", encoding="utf-8")
    _write_json(contract_dir / "stability_doctrine.json", {"schema_version": 1})
    _write_json(contract_dir / "artifact_metadata.json", {"sha": "sha"})
    with pytest.raises(json.JSONDecodeError):
        emit_manifest(contract_dir, git_sha="sha", created_at="time")
    assert not (contract_dir / "contract_manifest.json").exists()
