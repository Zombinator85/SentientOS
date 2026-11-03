from __future__ import annotations

import json
import os
from pathlib import Path

from scripts import editable_install


class DummyDist:
    def __init__(self, direct_url: str | None) -> None:
        self._direct_url = direct_url

    def read_text(self, filename: str) -> str | None:
        if filename != "direct_url.json":
            return None
        return self._direct_url


def test_direct_url_editable_matches_repo(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    direct_url = json.dumps({
        "url": repo_root.as_uri(), "dir_info": {"editable": True}
    })
    monkeypatch.setattr(
        editable_install.metadata,
        "distribution",
        lambda _name: DummyDist(direct_url),
    )

    status = editable_install.get_editable_install_status(repo_root)

    assert status.ok is True
    assert status.reason == "direct-url"


def test_direct_url_editable_mismatch_repo(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    other_root = tmp_path / "other"
    other_root.mkdir()
    direct_url = json.dumps({
        "url": other_root.as_uri(), "dir_info": {"editable": True}
    })
    monkeypatch.setattr(
        editable_install.metadata,
        "distribution",
        lambda _name: DummyDist(direct_url),
    )

    status = editable_install.get_editable_install_status(repo_root)

    assert status.ok is False
    assert status.reason == "direct-url-mismatch"


def test_module_path_fallback_matches_repo(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    module_path = repo_root / "sentientos" / "__init__.py"
    module_path.parent.mkdir()
    module_path.write_text("")

    monkeypatch.setattr(
        editable_install.metadata,
        "distribution",
        lambda _name: DummyDist(None),
    )

    class DummyModule:
        __file__ = str(module_path)

    monkeypatch.setattr(
        editable_install.importlib,
        "import_module",
        lambda _name: DummyModule,
    )

    status = editable_install.get_editable_install_status(repo_root)

    assert status.ok is True
    assert status.reason == "module-path-fallback"


def test_module_path_fallback_mismatch_repo(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    other_root = tmp_path / "other"
    other_root.mkdir()
    module_path = other_root / "sentientos" / "__init__.py"
    module_path.parent.mkdir()
    module_path.write_text("")

    monkeypatch.setattr(
        editable_install.metadata,
        "distribution",
        lambda _name: DummyDist(None),
    )

    class DummyModule:
        __file__ = str(module_path)

    monkeypatch.setattr(
        editable_install.importlib,
        "import_module",
        lambda _name: DummyModule,
    )

    status = editable_install.get_editable_install_status(repo_root)

    assert status.ok is False
    assert status.reason == "module-path-mismatch"


def test_windows_drive_file_url_is_decoded_for_the_host_platform():
    parsed = editable_install._path_from_url("file:///C:/SentientOS-edge")
    if os.name == "nt":
        assert parsed == Path("C:/SentientOS-edge")
    else:
        assert parsed == Path("/C:/SentientOS-edge")
