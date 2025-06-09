from __future__ import annotations

import ast
import hashlib
import importlib.util
from pathlib import Path
from typing import Iterable, Set

from mypy import api as mypy_api

from .cache import LintCache


def _file_hash(path: Path) -> str:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except Exception:
        return ""


def _discover_deps(path: Path, root: Path) -> Set[Path]:
    deps: Set[Path] = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return deps
    for node in ast.walk(tree):
        mod: str | None = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if mod:
                    spec = importlib.util.find_spec(mod)
                    if spec and spec.origin and spec.origin.endswith(".py"):
                        p = Path(spec.origin).resolve()
                        if root in p.parents:
                            deps.add(p)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = node.module
                spec = importlib.util.find_spec(mod)
                if spec and spec.origin and spec.origin.endswith(".py"):
                    p = Path(spec.origin).resolve()
                    if root in p.parents:
                        deps.add(p)
    return deps


def run_incremental(
    files: Iterable[Path],
    cache: LintCache,
    *,
    strict: bool = True,
    force_full: bool = False,

) -> tuple[list[str], Set[Path]]:
    """Run mypy on changed files and update cache.

    Returns the list of mypy messages and the set of files that were type checked."""

    root = cache.root
    changed: Set[Path] = set()

    for f in files:
        key = str(f)
        current = _file_hash(f)
        info = cache.data.get(key, {})
        if force_full or info.get("mypy") != current:
            changed.add(f)
            continue
        for dep in _discover_deps(f, root):
            dep_key = str(dep)
            dep_hash = _file_hash(dep)
            dep_info = cache.data.get(dep_key, {})
            if dep_info.get("mypy") != dep_hash:
                changed.add(f)
                break

    if not changed:
        return [], set()

    args = ["--show-traceback"]
    if strict:
        args.append("--strict")
    args.extend(str(p) for p in sorted(changed))
    out, err, status = mypy_api.run(args)

    issues: list[str] = []
    if status == 0:
        for f in changed:
            cache.data.setdefault(str(f), {})["mypy"] = _file_hash(f)
        return [], changed

    if out:
        issues.extend(out.strip().splitlines())
    if err:
        issues.extend(err.strip().splitlines())
    return issues, changed
