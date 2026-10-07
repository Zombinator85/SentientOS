from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

pytestmark = pytest.mark.no_legacy_skip


def _isolated_import(module: str, tmp_path: Path) -> dict[str, object]:
    code = dedent(
        """
        import importlib, json, os, pathlib, sys
        calls = []
        privilege = importlib.import_module("sentientos.privilege")
        privilege.require_admin_banner = lambda: calls.append("admin")
        privilege.require_lumos_approval = lambda: calls.append("lumos")
        sys.modules.pop("api.actuator", None)
        sys.modules.pop("api", None)
        module = importlib.import_module(sys.argv[1])
        paths = [os.environ["SENTIENTOS_LOG_DIR"], os.environ["ACT_SANDBOX"]]
        print(json.dumps({
            "calls": calls,
            "created": [path for path in paths if pathlib.Path(path).exists()],
            "plugins": getattr(module, "PLUGINS_INFO", {}),
            "worker": getattr(module, "_worker_started", False),
        }))
        """
    )
    env = os.environ.copy()
    env.update(
        SENTIENTOS_LOG_DIR=str(tmp_path / "logs"),
        ACT_SANDBOX=str(tmp_path / "sandbox"),
        ACT_PLUGINS_DIR=str(tmp_path / "plugins"),
        AUTONOMOUS_CALLS_LOG=str(tmp_path / "autonomous.jsonl"),
    )
    completed = subprocess.run(
        [sys.executable, "-c", code, module], env=env, text=True, capture_output=True, check=True
    )
    return json.loads(completed.stdout)


def test_scripts_lock_import_is_inert(monkeypatch):
    import sentientos.privilege as privilege
    calls = []
    monkeypatch.setattr(privilege, "require_admin_banner", lambda: calls.append("admin"))
    monkeypatch.setattr(privilege, "require_lumos_approval", lambda: calls.append("lumos"))
    sys.modules.pop("scripts.lock", None)
    importlib.import_module("scripts.lock")
    assert calls == []


@pytest.mark.parametrize("module_name", ["experiment_tracker", "privilege_lint_cli", "plugin_bus", "gui_stub"])
def test_privilege_sensitive_library_imports_are_inert(monkeypatch, module_name):
    import sentientos.privilege as privilege

    calls = []
    monkeypatch.setattr(privilege, "require_admin_banner", lambda: calls.append("admin"))
    monkeypatch.setattr(privilege, "require_lumos_approval", lambda: calls.append("lumos"))
    monkeypatch.setattr(privilege, "require_covenant_alignment", lambda: calls.append("covenant"))
    sys.modules.pop(module_name, None)

    importlib.import_module(module_name)

    assert calls == []


def test_privilege_lint_cli_main_enforces_guards_before_argument_handling(monkeypatch):
    import sentientos.privilege as privilege

    calls = []
    monkeypatch.setattr(privilege, "require_admin_banner", lambda: calls.append("admin"))
    monkeypatch.setattr(privilege, "require_lumos_approval", lambda: calls.append("lumos"))
    sys.modules.pop("privilege_lint_cli", None)
    cli = importlib.import_module("privilege_lint_cli")
    monkeypatch.setattr(cli, "require_admin_banner", lambda: calls.append("admin"))
    monkeypatch.setattr(cli, "require_lumos_approval", lambda: calls.append("lumos"))

    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])

    assert exc.value.code == 0
    assert calls == ["admin", "lumos"]


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="requires a non-root POSIX worker")
def test_privilege_lint_cli_direct_execution_denies_non_admin_before_help():
    cli_path = Path(__file__).resolve().parents[1] / "privilege_lint_cli.py"
    completed = subprocess.run(
        [sys.executable, str(cli_path), "--help"],
        cwd=cli_path.parent,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "Access denied: run as Administrator" in completed.stderr


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="requires a non-root POSIX worker")
@pytest.mark.parametrize(
    ("script", "action"),
    [
        ("scripts/verify_audits.py", ["--strict"]),
        ("scripts/audit_immutability_verifier.py", ["--allow-missing-manifest"]),
    ],
)
def test_audit_cli_keeps_privilege_at_execution_boundary(script, action):
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / script
    help_result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr

    action_result = subprocess.run(
        [sys.executable, str(script_path), *action],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert action_result.returncode != 0
    assert "Access denied: run as Administrator" in action_result.stderr


def test_control_plane_federation_import_path_is_inert(tmp_path):
    code = dedent(
        """
        import importlib, json
        import sentientos.privilege as privilege
        calls = []
        privilege.require_admin_banner = lambda: calls.append("admin")
        privilege.require_lumos_approval = lambda: calls.append("lumos")
        privilege.require_covenant_alignment = lambda: calls.append("covenant")
        importlib.import_module("control_plane.records")
        print(json.dumps(calls))
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
        text=True, capture_output=True, check=True,
    )

    assert json.loads(completed.stdout) == []


def test_scripts_lock_check_is_unprivileged(monkeypatch, tmp_path):
    import scripts.lock as lock
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(lock, "LOCKS", ())
    monkeypatch.setattr(lock, "require_admin_banner", lambda: pytest.fail("authorization called"))
    monkeypatch.setattr(lock, "require_lumos_approval", lambda: pytest.fail("authorization called"))
    lock.check()


def test_scripts_lock_effects_authorize_before_mutation(monkeypatch):
    import scripts.lock as lock
    events = []
    monkeypatch.setattr(lock, "require_admin_banner", lambda: events.append("admin"))
    monkeypatch.setattr(lock, "require_lumos_approval", lambda: events.append("lumos"))
    monkeypatch.setattr(lock.subprocess, "check_call", lambda *_a, **_k: events.append("effect"))
    monkeypatch.setattr(lock, "LOCKS", ("lock",))
    lock.install()
    assert events[:3] == ["admin", "lumos", "effect"]


def test_api_package_import_is_inert(tmp_path):
    result = _isolated_import("api", tmp_path)
    assert result == {"calls": [], "created": [], "plugins": {}, "worker": False}


def test_actuator_import_has_no_privilege_or_runtime_effects(tmp_path):
    result = _isolated_import("api.actuator", tmp_path)
    assert result == {"calls": [], "created": [], "plugins": {}, "worker": False}


def test_actuator_import_does_not_create_log_directory(tmp_path):
    _isolated_import("api.actuator", tmp_path)
    assert not (tmp_path / "logs").exists()
    assert not (tmp_path / "autonomous.jsonl").exists()


def test_actuator_autonomous_log_directory_is_created_only_at_write_boundary(monkeypatch, tmp_path):
    import api.actuator as actuator

    autonomous_log = tmp_path / "nested" / "autonomous.jsonl"
    monkeypatch.setattr(actuator, "AUTONOMOUS_LOG", autonomous_log)
    monkeypatch.setattr(actuator, "act", lambda *_a, **_k: {})
    audit = type("Audit", (), {"log_entry": staticmethod(lambda **_kwargs: None)})
    monkeypatch.setitem(sys.modules, "autonomous_audit", audit)
    assert not autonomous_log.parent.exists()
    actuator.auto_call({"type": "proof"})
    assert autonomous_log.exists()


def test_actuator_protected_effects_authorize_before_execution(monkeypatch, tmp_path):
    import api.actuator as actuator
    events = []
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: events.append("authorize"))
    monkeypatch.setattr(actuator, "SANDBOX_DIR", tmp_path)
    actuator.file_write("proof.txt", "ok")
    assert events == ["authorize"]
    assert (tmp_path / "proof.txt").read_text() == "ok"


def test_external_plugins_are_rejected_without_execution(monkeypatch, tmp_path):
    plugin_dir = tmp_path / "plugins"; plugin_dir.mkdir()
    marker = tmp_path / "marker"
    (plugin_dir / "sample.py").write_text(
        f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\n'
        'def register(register):\n register("sample", object())\n'
    )
    import api.actuator as actuator
    monkeypatch.setenv("ACT_PLUGINS_DIR", str(plugin_dir))
    assert "sample" not in actuator.ACTUATORS
    with pytest.raises(RuntimeError, match="external actuator plugins are disabled"):
        actuator.initialize_actuators(load_external_plugins=True)
    assert "sample" not in actuator.ACTUATORS
    assert not marker.exists()
