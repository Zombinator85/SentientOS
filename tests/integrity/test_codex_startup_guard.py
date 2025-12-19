from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

from sentientos.codex_startup_guard import (
    CodexProvenanceViolation,
    CodexStartupReentryError,
    CodexStartupViolation,
)


def _run_python(script: str, *, authorize_startup: bool) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if authorize_startup:
        env.pop("CODEX_STARTUP_ROOT_PID", None)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
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
