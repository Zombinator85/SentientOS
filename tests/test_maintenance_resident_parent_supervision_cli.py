from __future__ import annotations

import pytest

from sentientos import maintenance_resident_parent_supervision as parent
from sentientos import maintenance_initial_posix_resident_commissioning as commissioning


def test_parent_entrypoint_requires_explicit_config(monkeypatch) -> None:
    called = False

    def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("configuration loading must not run without an explicit path")

    monkeypatch.setattr(commissioning, "verify_commissioned_resident_config", forbidden)
    with pytest.raises(SystemExit) as error:
        parent.main([])
    assert error.value.code == 2
    assert called is False


def test_parent_entrypoint_rejects_relative_config_before_loading(monkeypatch) -> None:
    loaded = False

    def forbidden(*args, **kwargs):
        nonlocal loaded
        loaded = True
        raise AssertionError("relative paths are not accepted")

    monkeypatch.setattr(commissioning, "verify_commissioned_resident_config", forbidden)
    assert parent.main(["--config", "resident.json"]) == 2
    assert loaded is False


def test_parent_origin_requires_exact_configured_repository_and_interpreter(tmp_path) -> None:
    repository = tmp_path / "repository"
    package = repository / "sentientos"
    package.mkdir(parents=True)
    module = package / "maintenance_resident_parent_supervision.py"
    module.write_text("# parent owner")
    interpreter = tmp_path / "python"
    interpreter.write_text("interpreter identity fixture")
    other_interpreter = tmp_path / "other-python"
    other_interpreter.write_text("substituted interpreter fixture")
    working_directory = repository
    config = {
        "repository_root": str(repository),
        "python_executable": str(interpreter),
        "working_directory": str(working_directory),
    }

    parent._verify_parent_invocation_origin(
        config, executable=interpreter, working_directory=working_directory,
        module_path=module)
    with pytest.raises(ValueError, match="resident_parent_process_origin_mismatch"):
        parent._verify_parent_invocation_origin(
            config, executable=other_interpreter,
            working_directory=working_directory, module_path=module)
