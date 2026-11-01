from __future__ import annotations

from pathlib import Path

import pytest

from sentientos.audit_sink import resolve_audit_paths

pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize(
    ("value", "expected"),
    [("baseline", "baseline"), ("runtime", "runtime"), ("both", "both"), ("unknown", "runtime")],
)
def test_audit_mode_is_normalized_to_supported_literal(value: str, expected: str) -> None:
    config = resolve_audit_paths(
        repo_root=Path("/repo"),
        env={"SENTIENTOS_AUDIT_MODE": value},
    )

    assert config.mode == expected
