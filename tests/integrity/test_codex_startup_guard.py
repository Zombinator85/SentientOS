from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from codex.integrity_daemon import IntegrityDaemon
from sentientos.codex_startup_guard import (
    CodexProvenanceViolation,
    CodexStartupViolation,
    codex_startup_phase,
)


def test_governance_entrypoints_allowed_during_startup(tmp_path: Path) -> None:
    with codex_startup_phase():
        daemon = IntegrityDaemon(tmp_path)

    assert daemon.health()["daemon"] == "IntegrityDaemon"


def test_governance_entrypoints_block_runtime(tmp_path: Path) -> None:
    with codex_startup_phase():
        pass

    with pytest.raises(CodexStartupViolation):
        IntegrityDaemon(tmp_path)


def test_provenance_allows_registered_bootstrap(tmp_path: Path) -> None:
    # This test module is permitted via the tests.* allowlist entry.
    with codex_startup_phase():
        daemon = IntegrityDaemon(tmp_path)

    assert daemon.health()["daemon"] == "IntegrityDaemon"


def test_provenance_blocks_unregistered_startup_call(tmp_path: Path, tmp_path_factory) -> None:
    rogue_script = tmp_path_factory.mktemp("rogue_startup") / "rogue_bootstrap.py"
    rogue_script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "from codex.integrity_daemon import IntegrityDaemon",
                "from sentientos.codex_startup_guard import codex_startup_phase",
                f"with codex_startup_phase():",
                f"    IntegrityDaemon(Path({repr(str(tmp_path))}))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(CodexProvenanceViolation):
        runpy.run_path(str(rogue_script), run_name="rogue.startup")
