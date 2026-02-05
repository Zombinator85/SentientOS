from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class EditableInstallStatus:
    ok: bool
    reason: str


def _path_from_url(url: str) -> Path | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"", "file"}:
        return None
    if parsed.scheme == "file":
        raw_path = parsed.path
    else:
        raw_path = parsed.path or parsed.netloc
    if not raw_path:
        return None
    return Path(unquote(raw_path))


def _paths_match(candidate: Path, repo_root: Path) -> bool:
    try:
        return candidate.resolve() == repo_root.resolve()
    except FileNotFoundError:
        return False


def _module_path(module_name: str) -> Path | None:
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return None
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return None
    return Path(module_file)


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _read_direct_url(dist: metadata.Distribution) -> dict[str, Any] | None:
    direct_url_text = dist.read_text("direct_url.json")
    if not direct_url_text:
        return None
    try:
        return json.loads(direct_url_text)
    except json.JSONDecodeError:
        return None


def get_editable_install_status(
    repo_root: Path, dist_name: str = "sentientos"
) -> EditableInstallStatus:
    repo_root = repo_root.resolve()
    try:
        dist = metadata.distribution(dist_name)
    except metadata.PackageNotFoundError:
        return EditableInstallStatus(False, "distribution-not-found")

    direct_url = _read_direct_url(dist)
    if direct_url is not None:
        dir_info = direct_url.get("dir_info", {})
        if dir_info.get("editable") is not True:
            return EditableInstallStatus(False, "direct-url-not-editable")
        url = direct_url.get("url")
        if not url:
            return EditableInstallStatus(False, "direct-url-missing")
        direct_path = _path_from_url(url)
        if direct_path is None or not _paths_match(direct_path, repo_root):
            return EditableInstallStatus(False, "direct-url-mismatch")
        return EditableInstallStatus(True, "direct-url")

    module_file = _module_path(dist_name)
    if module_file is None:
        return EditableInstallStatus(False, "module-path-missing")
    if _is_within(module_file, repo_root):
        return EditableInstallStatus(True, "module-path-fallback")
    return EditableInstallStatus(False, "module-path-mismatch")


def editable_install_from_repo_root(
    repo_root: Path, dist_name: str = "sentientos"
) -> bool:
    return get_editable_install_status(repo_root, dist_name).ok
