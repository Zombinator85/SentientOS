from __future__ import annotations

import json
import os
import sys
import time
import subprocess
import pytest
import shlex
from pathlib import Path

from scripts.codex_finalize_landing import (
    _create_invocation_context,
    _run_stage,
    _terminal_directory_custody,
)
from sentientos.codex_landing_evidence_binding import (
    create_commit_binding,
    create_workspace_binding,
    verify_commit_matches_workspace,
)

pytestmark = pytest.mark.no_legacy_skip


def _trust_command(result_path: Path) -> str:
    code = (
        "import json, os, pathlib; "
        "import trust_engine; "
        "trust_engine.log_event('validation', 'test', 'custody proof', 'pytest'); "
        f"pathlib.Path({str(result_path)!r}).write_text(json.dumps("
        "{'log': os.environ['SENTIENTOS_LOG_DIR'], 'trust': os.environ['TRUST_DIR']}))"
    )
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


def test_process_real_trust_output_stays_outside_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    result_path = tmp_path / "effective.json"
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(repo / "logs"))
    monkeypatch.setenv("TRUST_DIR", str(repo / "logs" / "trust"))
    context = _create_invocation_context(str(repo), str(tmp_path / "custody"), "test")

    result, runtime = _run_stage(
        "trust_proof", _trust_command(result_path), True, False, 30,
        time.monotonic() + 30, context.child_environment,
    )

    effective = json.loads(result_path.read_text(encoding="utf-8"))
    trust_root = Path(effective["trust"])
    assert result.exit_code == 0 and runtime.status == "passed"
    assert effective == {"log": context.child_log_root, "trust": context.child_trust_root}
    assert trust_root == Path(context.child_log_root) / "trust"
    assert (trust_root / "events.jsonl").is_file()
    assert repo not in trust_root.parents and not (repo / "logs").exists()
    assert os.environ["TRUST_DIR"] == str(repo / "logs" / "trust")


def test_hostile_ambient_log_destinations_are_overridden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("SENTIENTOS_LOG_DIR", str(repo / "logs"))
    monkeypatch.setenv("TRUST_DIR", str(repo / "logs" / "trust"))
    context = _create_invocation_context(str(repo), None, "hostile")
    assert context.child_environment["SENTIENTOS_LOG_DIR"] == context.child_log_root
    assert context.child_environment["TRUST_DIR"] == context.child_trust_root
    assert Path(context.child_trust_root).parent == Path(context.child_log_root)
    assert repo not in Path(context.child_log_root).parents


def test_log_custody_identity_is_verified_terminally(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    context = _create_invocation_context(str(repo), str(tmp_path / "custody"), "identity")
    terminal, reasons = _terminal_directory_custody(context)
    assert reasons == []
    assert terminal["logs"]["identity_status"] == "unchanged"
    assert terminal["logs"]["inode"] == context.directory_custody_initial["logs"]["inode"]


def test_workspace_generated_prefixes_do_not_hide_repository_logs() -> None:
    from scripts.codex_finalize_landing import GENERATED_PREFIXES

    assert "logs/" not in GENERATED_PREFIXES
    source = Path("scripts/codex_finalize_landing.py").read_text(encoding="utf-8")
    assert '"SENTIENTOS_LOG_DIR": str(logs)' in source
    assert '"TRUST_DIR": str(trust)' in source


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, text=True, capture_output=True).stdout.strip()


def test_precommit_commit_postcommit_pairing_excludes_generated_logs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    intended = repo / "change.py"
    intended.write_text("before = True\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    intended.write_text("after = True\n", encoding="utf-8")
    context = _create_invocation_context(str(repo), str(tmp_path / "custody"), "pair")
    result_path = tmp_path / "effective.json"
    result, _runtime = _run_stage("trust_pair", _trust_command(result_path), True, False, 30, time.monotonic() + 30, context.child_environment)
    assert result.exit_code == 0
    workspace = create_workspace_binding(repo, intended_paths=["change.py"], intended_commit_title="change")
    _git(repo, "add", "change.py")
    _git(repo, "commit", "-m", "change")
    commit = create_commit_binding(repo, workspace_binding=workspace)
    assert verify_commit_matches_workspace(repo, workspace.to_dict(), commit.to_dict()).status == "landing_evidence_binding_ready"
    assert _git(repo, "show", "--name-only", "--format=", "HEAD") == "change.py"
    assert not (repo / "logs").exists()


def test_unexpected_repository_log_path_remains_blocking(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "change.py").write_text("before = True\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    (repo / "change.py").write_text("after = True\n", encoding="utf-8")
    (repo / "logs").mkdir()
    (repo / "logs" / "unexpected.jsonl").write_text("{}\n", encoding="utf-8")
    try:
        create_workspace_binding(repo, intended_paths=["change.py"], intended_commit_title="change")
    except ValueError as exc:
        assert "unknown_dirty_paths" in str(exc)
    else:
        raise AssertionError("repository-local logs must remain visible")
