from __future__ import annotations

import importlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip


@pytest.mark.parametrize(
    ("module_name", "function_name"),
    [
        ("scripts.ritual_header_repair", "fix_file"),
        ("fix_header_subset", "process_file"),
        ("scripts.fix_header_subset", "process_file"),
    ],
)
def test_header_tools_only_authorize_at_file_write_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    module_name: str,
    function_name: str,
) -> None:
    module = importlib.import_module(module_name)
    events: list[str] = []
    monkeypatch.setattr(module, "require_admin_banner", lambda: events.append("admin"))
    monkeypatch.setattr(module, "require_lumos_approval", lambda: events.append("lumos"))

    target = tmp_path / "sample.py"
    target.write_text("value = 1\n", encoding="utf-8")
    original_write_text = Path.write_text

    def observe_write(path: Path, *args: object, **kwargs: object) -> int:
        if path == target:
            events.append("write")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", observe_write)
    getattr(module, function_name)(target)

    assert events == ["admin", "lumos", "write"]
    result = target.read_text(encoding="utf-8")
    assert "require_admin_banner()" not in result
    assert "require_lumos_approval()" not in result
    assert '"""Sanctuary Privilege Ritual' not in result
