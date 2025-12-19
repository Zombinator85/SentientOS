from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from sentientos.codex_startup_guard import (
    CodexProvenanceViolation,
    CodexStartupReentryError,
    CodexStartupViolation,
)

pytestmark = pytest.mark.no_legacy_skip


def _run_python(script: str, *, authorize_startup: bool) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if authorize_startup:
        env.pop("CODEX_STARTUP_ROOT_PID", None)
        env.pop("CODEX_STARTUP_FINALIZED", None)
    prelude = """
    import json
    import sys
    import types

    if "yaml" not in sys.modules:
        yaml_stub = types.ModuleType("yaml")

        def _safe_yaml(text=None, *_, **__):
            if not text:
                return {}
            try:
                return json.loads(text)
            except Exception:
                return {}

        yaml_stub.safe_load = _safe_yaml
        sys.modules["yaml"] = yaml_stub

    if "pdfrw" not in sys.modules:
        pdfrw_stub = types.ModuleType("pdfrw")
        pdfrw_stub.PdfDict = dict
        pdfrw_stub.PdfReader = lambda *_a, **_k: None
        pdfrw_stub.PdfWriter = type(
            "PdfWriterStub",
            (),
            {
                "addpage": lambda *_a, **_k: None,
                "write": lambda *_a, **_k: None,
            },
        )
        sys.modules["pdfrw"] = pdfrw_stub
    """
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(prelude + script)],
        capture_output=True,
        text=True,
        env=env,
    )


def test_governance_entrypoints_allowed_during_startup(tmp_path: Path) -> None:
    script = f"""
    from pathlib import Path
    from codex.integrity_daemon import IntegrityDaemon
    from sentientos.codex_startup_guard import codex_startup_phase

    __name__ = "tests.codex.startup"
    with codex_startup_phase():
        daemon = IntegrityDaemon(Path({repr(str(tmp_path))}))
    print(daemon.health()["daemon"])
    """

    result = _run_python(script, authorize_startup=True)
    assert result.returncode == 0
    assert "IntegrityDaemon" in result.stdout


def test_governance_entrypoints_block_runtime(tmp_path: Path) -> None:
    script = f"""
    from pathlib import Path
    from codex.integrity_daemon import IntegrityDaemon

    IntegrityDaemon(Path({repr(str(tmp_path))}))
    """

    result = _run_python(script, authorize_startup=True)
    assert result.returncode != 0
    assert CodexStartupViolation.__name__ in result.stderr


def test_provenance_allows_registered_bootstrap(tmp_path: Path) -> None:
    script = f"""
    from pathlib import Path
    from codex.integrity_daemon import IntegrityDaemon
    from sentientos.codex_startup_guard import codex_startup_phase

    __name__ = "tests.codex.startup"
    with codex_startup_phase():
        daemon = IntegrityDaemon(Path({repr(str(tmp_path))}))
    print(daemon.health()["daemon"])
    """

    result = _run_python(script, authorize_startup=True)
    assert result.returncode == 0
    assert "IntegrityDaemon" in result.stdout


def test_provenance_blocks_unregistered_startup_call(tmp_path: Path) -> None:
    script = f"""
    from pathlib import Path
    from codex.integrity_daemon import IntegrityDaemon
    from sentientos.codex_startup_guard import codex_startup_phase

    __name__ = "rogue.startup"
    with codex_startup_phase():
        IntegrityDaemon(Path({repr(str(tmp_path))}))
    """

    result = _run_python(script, authorize_startup=True)
    assert result.returncode != 0
    assert CodexProvenanceViolation.__name__ in result.stderr


def test_nested_startup_is_rejected() -> None:
    script = """
    from sentientos.codex_startup_guard import codex_startup_phase

    __name__ = "tests.codex.startup"
    with codex_startup_phase():
        with codex_startup_phase():
            pass
    """

    result = _run_python(script, authorize_startup=True)
    assert result.returncode != 0
    assert CodexStartupReentryError.__name__ in result.stderr


def test_reentry_after_finalization_is_rejected() -> None:
    script = """
    from sentientos.codex_startup_guard import codex_startup_phase

    __name__ = "tests.codex.startup"
    with codex_startup_phase():
        pass

    with codex_startup_phase():
        pass
    """

    result = _run_python(script, authorize_startup=True)
    assert result.returncode != 0
    assert CodexStartupReentryError.__name__ in result.stderr


def test_governance_entrypoints_blocked_after_finalization(tmp_path: Path) -> None:
    script = f"""
    from pathlib import Path
    from codex.integrity_daemon import IntegrityDaemon
    from sentientos.codex_startup_guard import codex_startup_phase

    __name__ = "tests.codex.startup"
    with codex_startup_phase():
        pass

    IntegrityDaemon(Path({repr(str(tmp_path))}))
    """

    result = _run_python(script, authorize_startup=True)
    assert result.returncode != 0
    assert CodexStartupViolation.__name__ in result.stderr


def test_child_process_starts_finalized_by_default() -> None:
    script = """
    from sentientos.codex_startup_guard import codex_startup_phase

    with codex_startup_phase():
        pass
    """

    result = _run_python(script, authorize_startup=False)
    assert result.returncode != 0
    assert CodexStartupReentryError.__name__ in result.stderr


def test_startup_state_is_observable_and_read_only() -> None:
    script = """
    import importlib
    import json
    import sentientos.codex_startup_guard as guard
    from sentientos.codex_startup_guard import codex_startup_phase, codex_startup_state

    __name__ = "tests.codex.startup"
    def snapshot():
        state = codex_startup_state()
        return {
            "active": state.active,
            "finalized": state.finalized,
            "owner_pid": state.owner_pid,
            "root_pid": state.root_pid,
        }

    observations = []
    observations.append(snapshot())
    with codex_startup_phase():
        observations.append(snapshot())

    frozen_state = codex_startup_state()
    try:
        frozen_state.finalized = False
        read_only = False
    except Exception:
        read_only = True

    guard._STARTUP_FINALIZED = False
    reloaded_guard = importlib.reload(guard)
    state_after_reload = reloaded_guard.codex_startup_state()
    observations.append(
        {
            "active": state_after_reload.active,
            "finalized": state_after_reload.finalized,
            "owner_pid": state_after_reload.owner_pid,
            "root_pid": state_after_reload.root_pid,
        }
    )
    print(json.dumps({"observations": observations, "read_only": read_only}))
    """

    result = _run_python(script, authorize_startup=True)
    assert result.returncode == 0
    payload = json.loads(result.stdout.strip())
    assert payload["read_only"] is True
    observations = payload["observations"]
    assert len(observations) == 3
    owner_pid = observations[0]["owner_pid"]
    root_pid = observations[0]["root_pid"]
    assert observations[0]["active"] is False
    assert observations[0]["finalized"] is False
    assert observations[1]["active"] is True
    assert observations[1]["finalized"] is False
    assert observations[2]["active"] is False
    assert observations[2]["finalized"] is True
    assert observations[1]["owner_pid"] == owner_pid
    assert observations[2]["owner_pid"] == owner_pid
    assert observations[1]["root_pid"] == root_pid
    assert observations[2]["root_pid"] == root_pid


def test_child_process_observes_finalized_state() -> None:
    script = """
    import json
    from sentientos.codex_startup_guard import codex_startup_state

    state = codex_startup_state()
    print(json.dumps({"active": state.active, "finalized": state.finalized}))
    """

    result = _run_python(script, authorize_startup=False)
    assert result.returncode == 0
    payload = json.loads(result.stdout.strip())
    assert payload == {"active": False, "finalized": True}
