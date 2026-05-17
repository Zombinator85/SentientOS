from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from scripts.run_workspace_file_effect import main

pytestmark = pytest.mark.no_legacy_skip


def _run(args: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(args)
    return code, out.getvalue()


def test_requires_workspace_root_and_target() -> None:
    with pytest.raises(SystemExit):
        main(["--payload", "x"])


def test_dry_run_writes_nothing_and_summary_prints(tmp_path: Path) -> None:
    code, stdout = _run(["--workspace-root", str(tmp_path), "--target", "demo.txt", "--payload", "hello", "--dry-run", "--summary"])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["single_target_only"] is True
    assert payload["writes_performed"] is False
    assert not (tmp_path / "demo.txt").exists()


def test_create_update_and_preimage_summary(tmp_path: Path) -> None:
    code, stdout = _run(["--workspace-root", str(tmp_path), "--target", "demo.txt", "--payload", "hello", "--summary"])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["effect"]["created_new_file"] is True
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "hello"
    code, stdout = _run(["--workspace-root", str(tmp_path), "--target", "demo.txt", "--payload", "updated"])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["preimage"]["preimage_status"] == "workspace_file_preimage_captured"
    assert payload["result"]["replaced_existing_file"] is True
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "updated"


def test_rollback_created_removes_exact_target(tmp_path: Path) -> None:
    sibling = tmp_path / "sibling.txt"
    sibling.write_text("keep", encoding="utf-8")
    code, stdout = _run(["--workspace-root", str(tmp_path), "--target", "rollback.txt", "--payload", "rollback me", "--rollback", "--summary"])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["rollback"]["status"] == "workspace_file_rollback_created_file_removed"
    assert not (tmp_path / "rollback.txt").exists()
    assert sibling.read_text(encoding="utf-8") == "keep"


def test_rollback_update_restores_exact_target(tmp_path: Path) -> None:
    (tmp_path / "demo.txt").write_text("old", encoding="utf-8")
    code, stdout = _run(["--workspace-root", str(tmp_path), "--target", "demo.txt", "--payload", "new", "--rollback", "--summary"])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["rollback"]["status"] == "workspace_file_rollback_preimage_restored"
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "old"


def test_refuses_absolute_path_traversal_symlink_and_directory(tmp_path: Path) -> None:
    for target in ["/tmp/out.txt", "../out.txt"]:
        code, _stdout = _run(["--workspace-root", str(tmp_path), "--target", target, "--payload", "x", "--summary"])
        assert code == 2
    (tmp_path / "real.txt").write_text("x", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(tmp_path / "real.txt")
    code, stdout = _run(["--workspace-root", str(tmp_path), "--target", "link.txt", "--payload", "x"])
    assert code == 2
    assert "symlink_target_write" in stdout
    (tmp_path / "dir").mkdir()
    code, stdout = _run(["--workspace-root", str(tmp_path), "--target", "dir", "--payload", "x"])
    assert code == 2
    assert "directory_target_write" in stdout


def test_summary_declares_no_subprocess_shell_network_provider_prompt(tmp_path: Path) -> None:
    code, stdout = _run(["--workspace-root", str(tmp_path), "--target", "demo.txt", "--payload", "x", "--summary"])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["network_performed"] is False
    assert payload["provider_invocation_performed"] is False
    assert payload["prompt_assembly_performed"] is False
    assert payload["subprocess_performed"] is False
    assert payload["shell_performed"] is False
