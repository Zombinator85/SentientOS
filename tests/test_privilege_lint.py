import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import privilege_lint as pl


def _assert_missing(issues):
    assert any("missing privilege docstring" in i for i in issues)
    assert any("require_admin_banner()" in i for i in issues)


def test_detect_daemon_pattern(tmp_path):
    path = tmp_path / "worker_daemon.py"
    path.write_text("print('hi')\n", encoding="utf-8")
    files = pl.find_entrypoints(tmp_path)
    assert path in files
    issues = pl.check_file(path)
    _assert_missing(issues)


def test_detect_main_block(tmp_path):
    path = tmp_path / "misc.py"
    path.write_text("if __name__ == '__main__':\n    pass\n", encoding="utf-8")
    files = pl.find_entrypoints(tmp_path)
    assert path in files
    issues = pl.check_file(path)
    _assert_missing(issues)


def test_detect_argparse_usage(tmp_path):
    path = tmp_path / "helper.py"
    path.write_text("import argparse\nparser = argparse.ArgumentParser()\n", encoding="utf-8")
    files = pl.find_entrypoints(tmp_path)
    assert path in files
    issues = pl.check_file(path)
    _assert_missing(issues)


def test_banner_not_immediate(tmp_path):
    path = tmp_path / "cli.py"
    path.write_text(
        "from admin_utils import require_admin_banner\n"
        f'"{pl.DOCSTRING}"\n'
        "print('hi')\n"
        "require_admin_banner()\n",
        encoding="utf-8",
    )
    issues = pl.check_file(path)
    assert any("require_admin_banner()" in i for i in issues)
