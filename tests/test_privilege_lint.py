#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/
from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""



import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import privilege_lint as pl
from pathlib import Path


def test_good_order(tmp_path: Path) -> None:
    path = tmp_path / "tool.py"
    content = "\n".join(pl.BANNER_ASCII + [
        pl.FUTURE_IMPORT,
        '"""doc"""',
        'import os',
    ])
    path.write_text(content, encoding="utf-8")
    linter = pl.PrivilegeLinter()
    assert linter.validate(path) == []


def test_missing_docstring(tmp_path: Path) -> None:
    path = tmp_path / "tool.py"
    content = "\n".join(pl.BANNER_ASCII + [
        pl.FUTURE_IMPORT,
        'import os',
    ])
    path.write_text(content, encoding="utf-8")
    linter = pl.PrivilegeLinter()
    assert linter.validate(path) == []


def test_bad_future_position(tmp_path: Path) -> None:
    path = tmp_path / "tool_cli.py"
    content = "\n".join(pl.BANNER_ASCII + [
        '"""doc"""',
        pl.FUTURE_IMPORT,
        'import os',
    ])
    path.write_text(content, encoding="utf-8")
    linter = pl.PrivilegeLinter()
    issues = linter.validate(path)
    assert any("Banner and __future__ import" in i for i in issues)


def test_main_block_in_tests_scanned(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    f = tests_dir / "cli.py"
    f.write_text('if __name__ == "__main__":\n    pass\n', encoding="utf-8")
    rc = pl.main([str(tmp_path), "--read-only", "--quiet"])
    assert rc == 1


def test_argparse_usage_in_tests_scanned(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    f = tests_dir / "cli.py"
    f.write_text('import argparse\nargparse.ArgumentParser()\n', encoding="utf-8")
    rc = pl.main([str(tmp_path), "--read-only", "--quiet"])
    assert rc == 1


def test_argparse_inside_test_function_is_not_a_cli_entrypoint(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    f = tests_dir / "test_fixture.py"
    f.write_text(
        "def test_cli_fixture():\n"
        "    import argparse\n"
        "    argparse.ArgumentParser()\n",
        encoding="utf-8",
    )
    rc = pl.main([str(tmp_path), "--read-only", "--quiet"])
    assert rc == 0


def test_privilege_lint_plugins_support_modern_entry_points(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from privilege_lint import plugins
    from privilege_lint.config import LintConfig

    def plugin(_path: Path, _config: LintConfig) -> list[str]:
        return []

    class ModernEntryPoints:
        def select(self, *, group: str) -> list[object]:
            assert group == "privilege_lint.plugins"
            return [type("EntryPoint", (), {"load": lambda self: plugin})()]

    monkeypatch.setattr(plugins, "entry_points", ModernEntryPoints)
    assert plugins.load_plugins() == [plugin]


def test_banner_missing_failure(tmp_path: Path) -> None:
    path = tmp_path / "tool_cli.py"
    path.write_text("\n".join([
        pl.FUTURE_IMPORT,
        "import argparse",
        "if __name__ == \"__main__\":",
        "    argparse.ArgumentParser().parse_args()",
    ]), encoding="utf-8")
    linter = pl.PrivilegeLinter()
    issues = linter.validate(path)
    assert any("banner" in i.lower() for i in issues)


def test_missing_admin_call(tmp_path: Path) -> None:
    path = tmp_path / "tool_cli.py"
    content = pl.BANNER_ASCII + [
        pl.FUTURE_IMPORT,
        "import argparse",
        "if __name__ == \"__main__\":",
        "    argparse.ArgumentParser().parse_args()",
    ]
    path.write_text("\n".join(content), encoding="utf-8")
    linter = pl.PrivilegeLinter()
    issues = linter.validate(path)


def test_read_only_mode_skips_privilege_gates_and_does_not_write_reports(monkeypatch, tmp_path: Path) -> None:
    import privilege_lint_cli as cli

    def denied() -> None:
        raise AssertionError("read-only lint must not request privilege")

    monkeypatch.setattr(cli, "require_admin_banner", denied)
    monkeypatch.setattr(cli, "require_lumos_approval", denied)
    assert cli.main([str(tmp_path), "--read-only", "--quiet"]) == 0
    assert not (tmp_path / ".git" / ".privilege_lint.gitcache").exists()


def test_mutating_lint_still_checks_privilege_before_scanning(monkeypatch, tmp_path: Path) -> None:
    import privilege_lint_cli as cli

    calls: list[str] = []

    def deny_after_admin() -> None:
        calls.append("approval")
        raise PermissionError("approval required")

    monkeypatch.setattr(cli, "require_admin_banner", lambda: calls.append("admin"))
    monkeypatch.setattr(cli, "require_lumos_approval", deny_after_admin)
    monkeypatch.setattr(cli, "run_lint", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("scan should be blocked by guard")))
    import pytest
    with pytest.raises(PermissionError, match="approval required"):
        cli.main([str(tmp_path), "--fix", "--quiet"])
    assert calls == ["admin", "approval"]


def test_configured_file_globs_bound_source_scan(tmp_path: Path) -> None:
    from privilege_lint_cli import iter_py_files

    cli = tmp_path / "tool_cli.py"
    cli.write_text("pass\n", encoding="utf-8")
    module = tmp_path / "ordinary_module.py"
    module.write_text("import argparse\n", encoding="utf-8")

    selected = iter_py_files([str(tmp_path)], file_globs=["*_cli.py"])
    assert selected == [cli]


def test_nested_docstring_does_not_block_module_imports(tmp_path: Path) -> None:
    path = tmp_path / "tool_cli.py"
    path.write_text(
        "\n".join(
            pl.BANNER_ASCII
            + [pl.FUTURE_IMPORT, "import os", "def main():", "    \"\"\"nested documentation\"\"\"", "    return os.name"]
        ),
        encoding="utf-8",
    )
    assert pl.PrivilegeLinter().validate(path) == []
