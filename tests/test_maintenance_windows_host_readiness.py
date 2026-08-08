from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentientos import maintenance_windows_host_readiness as readiness

pytestmark = pytest.mark.no_legacy_skip


def test_windows_live_canary_content_is_canonical() -> None:
    """Stable repository-native node used by the operator-triggered live canary."""
    target = Path(__file__).parent / "fixtures" / "maintenance_windows_live_canary.txt"
    assert target.read_text(encoding="utf-8") == readiness.CANARY_CONTENT


def _manifest(repo: Path, tmp_path: Path) -> dict[str, str]:
    outside = tmp_path / "custody"
    outside.mkdir()
    values = {field: str(outside / field) for field in readiness.FIELDS - {"schema_version"}}
    values.update({
        "repository_root": str(repo), "expected_repository_sha": "1" * 40,
        "python_executable": str(tmp_path / "Program Files" / "Python" / "python.exe"),
        "git_executable": str(tmp_path / "Program Files" / "Git" / "git.exe"),
        "codex_executable": str(tmp_path / "Program Files" / "Codex" / "codex.exe"),
        "canary_source_path": str(repo / "tests" / "fixtures" / "maintenance_windows_live_canary.txt"),
        "canary_allowed_path_boundary": str(repo / "tests" / "fixtures"),
        "canary_validation_node": "tests/test_maintenance_windows_host_readiness.py::test_windows_live_canary_content_is_canonical",
        "tracked_remote": "origin", "tracked_base_ref": "main", "expected_task_name": "SentientOS Maintenance Wake",
    })
    return readiness.render_host_manifest(values)


def test_inspect_host_reports_missing_codex_and_does_not_read_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = tmp_path / "credentials.json"; secret.write_text("TOP-SECRET-TOKEN")
    monkeypatch.setattr(readiness, "_which", lambda name: None if name in {"codex", "pwsh", "powershell"} else "/bin/true")
    report = readiness.inspect_host(Path.cwd())
    assert report["codex"] == {"executable": None, "probe": None, "verified": False}
    assert report["codex_authentication"] == "unverified"
    assert "TOP-SECRET-TOKEN" not in json.dumps(report)
    assert report["credentials_inspected"] is False
    assert report["scheduler_mutation_performed"] is False


def test_manifest_is_closed_explicit_and_scope_is_bounded(tmp_path: Path) -> None:
    cfg = _manifest(Path.cwd(), tmp_path)
    assert readiness.verify_host_manifest(cfg)["status"] == "windows_host_manifest_verified"
    bad = dict(cfg); bad["canary_source_path"] = str(tmp_path / "other.txt")
    result = readiness.verify_host_manifest(bad)
    assert result["status"] == "windows_host_manifest_blocked"
    assert "canary_outside_allowed_path_boundary" in result["reason_codes"]
    with pytest.raises(ValueError, match="invalid_closed"):
        readiness.validate_manifest({**cfg, "token": "forbidden"})


def test_manual_canary_printer_is_argv_only_and_does_not_execute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _manifest(Path.cwd(), tmp_path)
    monkeypatch.setattr(readiness.subprocess, "run", lambda *a, **k: pytest.fail("executed"))
    result = readiness.print_manual_canary_command(cfg)
    assert result["executed"] is False and result["scheduler_mutation_performed"] is False
    assert all(item["shell"] is False and isinstance(item["argv"], list) for item in result["commands"])
    assert "schtasks" not in json.dumps(result).lower()


def test_inspect_canary_distinguishes_not_started_and_defect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Path.cwd(); cfg = _manifest(repo, tmp_path)
    canary = tmp_path / "canary.txt"; canary.write_text(readiness.CANARY_CONTENT)
    cfg["canary_source_path"] = str(canary); cfg["canary_allowed_path_boundary"] = str(tmp_path)
    monkeypatch.setattr(readiness, "_run", lambda *a, **k: {"returncode": 0, "stdout": ""})
    monkeypatch.setattr(readiness.wake, "load_config", lambda p: {})
    monkeypatch.setattr(readiness.wake, "inspect", lambda c: {"receipts": {"receipts": []}, "autonomy": {"next_action": "idle"}})
    assert readiness.inspect_canary(cfg)["status"] == "canary_not_started"
    canary.write_text("defect\n")
    assert readiness.inspect_canary(cfg)["status"] == "canary_defect_present"


def test_doctor_head_mismatch_and_dirty_tree_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _manifest(Path.cwd(), tmp_path)
    def fake(argv: object, *args: object, **kwargs: object) -> dict[str, object]:
        words = list(argv)  # type: ignore[arg-type]
        if words[-2:] == ["rev-parse", "HEAD"]: return {"returncode": 0, "stdout": "2" * 40}
        if words[-2:] == ["status", "--porcelain"]: return {"returncode": 0, "stdout": " M file"}
        return {"returncode": 0, "stdout": "ok"}
    monkeypatch.setattr(readiness, "_run", fake)
    result = readiness.doctor_live(cfg)
    assert result["status"] == "windows_host_blocked"
    assert {"repository_head_mismatch", "repository_dirty"}.issubset(result["reason_codes"])
    assert result["scheduler_mutation_performed"] is False
