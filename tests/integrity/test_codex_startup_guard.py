from __future__ import annotations

from pathlib import Path

import pytest

from codex.integrity_daemon import IntegrityDaemon
from sentientos.codex_startup_guard import CodexStartupViolation, codex_startup_phase


def test_governance_entrypoints_allowed_during_startup(tmp_path: Path) -> None:
    with codex_startup_phase():
        daemon = IntegrityDaemon(tmp_path)

    assert daemon.health()["daemon"] == "IntegrityDaemon"


def test_governance_entrypoints_block_runtime(tmp_path: Path) -> None:
    with codex_startup_phase():
        pass

    with pytest.raises(CodexStartupViolation):
        IntegrityDaemon(tmp_path)
