from __future__ import annotations

import re
from pathlib import Path
from typing import List

from typing import cast
from ._compat import RuleSkippedError, safe_import

esprima = safe_import("pyesprima", stub={"parseScript": None}, warn=False)


def _parse(path: Path) -> object | None:
    if getattr(esprima, "parseScript", None) is None:
        raise RuleSkippedError("missing dependency")
    try:
        return cast(
            object,
            esprima.parseScript(  # type: ignore[attr-defined]  # justified: optional dependency may lack stubs
                path.read_text(encoding="utf-8"), tolerant=True
            ),
        )
    except Exception:
        return None


def validate_js(path: Path, license_header: str | None = None) -> List[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    issues: List[str] = []
    if license_header and (not lines or license_header not in lines[0]):
        issues.append(f"{path}:1 missing license header")
    if lines and lines != sorted(lines, key=str) and any(l.startswith("import") for l in lines):
        # naive import sort check
        imports = [l for l in lines if l.startswith("import")]
        if imports != sorted(imports):
            ln = lines.index(imports[0]) + 1
            issues.append(f"{path}:{ln} imports not sorted")
    try:
        tree = _parse(path)
    except RuleSkippedError:
        raise
    if tree is None:
        return issues
    source = path.read_text(encoding="utf-8")
    # detect eval calls
    if "eval(" in source:
        for m in re.finditer(r"eval\(", source):
            ln = source[: m.start()].count("\n") + 1
            issues.append(f"{path}:{ln} avoid eval")
    # very naive unused variable check
    declared: dict[str, int] = {}
    for m in re.finditer(r"\bvar\s+(\w+)", source):
        name = m.group(1)
        line = source[: m.start()].count("\n") + 1
        declared[name] = line
    for m in re.finditer(r"\bconst\s+(\w+)", source):
        name = m.group(1)
        line = source[: m.start()].count("\n") + 1
        declared[name] = line
    for name in list(declared):
        if re.search(fr"\b{name}\b", source[source.find(name) + len(name) :]):
            del declared[name]
    for name, ln in declared.items():
        issues.append(f"{path}:{ln} unused variable {name}")
    return issues
