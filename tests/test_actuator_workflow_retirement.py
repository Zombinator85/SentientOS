from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

from api import actuator

pytestmark = pytest.mark.no_legacy_skip


def test_workflow_absent_from_builtin_registry() -> None:
    assert "workflow" not in actuator.BUILTIN_ACTUATOR_TYPES
    assert "workflow" not in actuator.ACTUATORS
    assert not hasattr(actuator, "WorkflowActuator")


def test_workflow_intent_has_zero_authorization_or_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: calls.append("authorize"))
    sys.modules.pop("workflow_controller", None)

    with pytest.raises(ValueError, match="Unsupported intent"):
        actuator.dispatch({"type": "workflow", "name": "anything"})

    assert calls == []
    assert "workflow_controller" not in sys.modules


def test_hostile_python_workflow_source_cannot_execute(tmp_path: Path) -> None:
    marker = tmp_path / "python-workflow-ran"
    hostile = tmp_path / "hostile.py"
    hostile.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding="utf-8")
    controller = importlib.import_module("workflow_controller")

    with pytest.raises(controller.WorkflowExecutionRetiredError):
        controller.load_workflow_file(str(hostile))

    assert not marker.exists()

    import workflow_library

    workflow_library.LIB_DIR = tmp_path
    with pytest.raises(FileNotFoundError):
        workflow_library.load_template("hostile")
    assert not marker.exists()


def test_hostile_dotted_action_module_cannot_import_or_execute(tmp_path: Path) -> None:
    marker = tmp_path / "hostile-module-imported"
    (tmp_path / "hostile_action.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\ndef run(): Path({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    script = "import workflow_controller as w; w.register_workflow('x', [{'action':'hostile_action.run'}])"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={"PYTHONPATH": os.pathsep.join((str(Path(__file__).resolve().parents[1]), str(tmp_path)))},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "WorkflowExecutionRetiredError" in result.stderr
    assert not marker.exists()


def test_callable_registry_is_unavailable_and_callable_is_inert(tmp_path: Path) -> None:
    controller = importlib.import_module("workflow_controller")
    marker = tmp_path / "callable-ran"

    with pytest.raises(controller.WorkflowExecutionRetiredError):
        controller.register_action("attack", lambda: marker.touch())

    assert not hasattr(controller, "ACTION_REGISTRY")
    assert not hasattr(controller, "WORKFLOWS")
    assert not marker.exists()


def test_controller_import_has_zero_privilege_or_filesystem_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sentientos.privilege as privilege

    calls: list[str] = []
    monkeypatch.setattr(privilege, "require_admin_banner", lambda: calls.append("admin"))
    monkeypatch.setattr(privilege, "require_lumos_approval", lambda: calls.append("lumos"))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("workflow_controller", None)
    before = set(tmp_path.iterdir())

    importlib.import_module("workflow_controller")

    assert calls == []
    assert set(tmp_path.iterdir()) == before


def test_controller_cli_and_reflex_bridge_are_retired(tmp_path: Path) -> None:
    marker = tmp_path / "reflex-ran"
    result = subprocess.run(
        [sys.executable, "workflow_controller.py", "--run-workflow", "run:reflex"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "WorkflowExecutionRetiredError" in result.stderr
    assert not marker.exists()


def test_unaffected_file_actuator_still_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actuator, "file_write", lambda path, content: {"ok": True, "path": path})
    assert actuator.dispatch({"type": "file", "path": "proof.txt", "content": "ok"}) == {
        "ok": True,
        "path": "proof.txt",
    }


def test_static_workflow_retirement_verifier() -> None:
    from scripts.verify_actuator_workflow_retirement import verify

    verify()
