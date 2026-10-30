"""Select when a main push needs a repeat of the strict Sphinx linkcheck."""

from __future__ import annotations

import argparse
import html
import re
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


_REPOSITORY_HOSTS = {"github.com", "raw.githubusercontent.com"}
_LINK_PATTERN = re.compile(r"https?://(?:github\.com|raw\.githubusercontent\.com)/[^\s<>\"']+")
_SOURCE_SUFFIXES = {".md", ".rst", ".txt", ".html"}
_PR_LINKCHECK_CONFIG_PATHS = {
    "Makefile",
    "pyproject.toml",
    "scripts/build_docs.py",
    "scripts/ci_linkcheck_scope.py",
    ".github/workflows/ci.yml",
}
_PR_AUTODOC_SOURCE_PATHS = {
    "sentientos/__init__.py",
    "sentientos/core.py",
    "sentientos/innerworld.py",
    "sentientos/orchestrator.py",
    "sentientos/privilege.py",
}


def _self_repository_targets(source_root: Path) -> set[str] | None:
    """Return paths referenced through the moving main ref, or None if unreadable."""
    sources = [
        path for path in source_root.rglob("*")
        if path.is_file() and path.suffix in _SOURCE_SUFFIXES
    ]
    if not sources:
        return None

    targets: set[str] = set()
    for source in sources:
        try:
            content = html.unescape(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            return None
        for match in _LINK_PATTERN.findall(content):
            url = urlsplit(match.rstrip(".,;:!?)]}"))
            if url.hostname not in _REPOSITORY_HOSTS:
                continue
            parts = [unquote(part) for part in url.path.split("/") if part]
            if (
                len(parts) < 3
                or parts[0].lower() != "zombinator85"
                or parts[1].lower() != "sentientos"
            ):
                continue
            if url.hostname == "github.com":
                if (
                    parts[2] not in {"blob", "tree", "raw"}
                    or len(parts) < 4
                    or parts[3] != "main"
                ):
                    continue
                target_parts = parts[4:]
            else:
                if parts[2] != "main":
                    continue
                target_parts = parts[3:]
            targets.add("/".join(target_parts))
    return targets


def main_link_targets_changed(
    source_root: Path, changed_paths: set[str]
) -> bool:
    """Return True when a changed path could affect a docs link to repository main."""
    targets = _self_repository_targets(source_root)
    if targets is None:
        return True
    normalized_changes = {
        PurePosixPath(path).as_posix().strip("/") for path in changed_paths
    }
    for target in targets:
        if not target:
            return bool(normalized_changes)
        if any(
            path == target or path.startswith(target.rstrip("/") + "/")
            for path in normalized_changes
        ):
            return True
    return False


def strict_main_linkcheck_required(
    source_root: Path, changed_paths: set[str] | None
) -> bool:
    """Fail closed when the push range cannot be inspected."""
    return changed_paths is None or main_link_targets_changed(source_root, changed_paths)


def strict_pull_request_linkcheck_required(
    source_root: Path, changed_paths: set[str] | None
) -> bool:
    """Run the full external linkcheck for documentation or its configuration changes.

    The documentation build still runs on every pull request. Unavailable base
    history fails closed so an uncertain diff cannot suppress the strict check.
    """
    if changed_paths is None:
        return True
    normalized_changes = {
        PurePosixPath(path).as_posix().strip("/") for path in changed_paths
    }
    if any(
        path == "docs"
        or path.startswith("docs/")
        or path in _PR_LINKCHECK_CONFIG_PATHS
        or path in _PR_AUTODOC_SOURCE_PATHS
        for path in normalized_changes
    ):
        return True
    return main_link_targets_changed(source_root, normalized_changes)


def changed_paths_between(base: str, head: str, *, repository_root: Path) -> set[str] | None:
    try:
        output = subprocess.run(
            ["git", "diff", "--name-only", "--no-renames", "-z", base, head],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {path for path in output.split("\0") if path}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--mode", choices=("push", "pull_request"), default="push")
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--output", default=None, help="GitHub Actions output file")
    args = parser.parse_args()
    root = Path(args.repository_root).resolve()
    changed = changed_paths_between(args.base, args.head, repository_root=root)
    required = (
        strict_pull_request_linkcheck_required(root / "docs", changed)
        if args.mode == "pull_request"
        else strict_main_linkcheck_required(root / "docs", changed)
    )
    line = f"required={'true' if required else 'false'}\n"
    if args.output:
        with Path(args.output).open("a", encoding="utf-8") as output:
            output.write(line)
    else:
        print(line, end="")
    if changed is None:
        print(
            "::warning::Unable to compare event base; running strict linkcheck fail-closed",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
