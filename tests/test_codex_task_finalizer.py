from __future__ import annotations

import pytest

from scripts.codex_finalize_landing import build_parser

pytestmark = pytest.mark.no_legacy_skip


def test_codex_task_finalizer_compatibility_parser_entrypoint() -> None:
    parser = build_parser()
    args = parser.parse_args(["finalize", "--phase", "pre-commit", "--title", "x", "--intended-commit-title", "x"])
    assert args.cmd == "finalize"
    assert args.phase == "pre-commit"
