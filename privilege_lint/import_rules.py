from __future__ import annotations

import sys
from pathlib import Path

_IMPORT_RE = ("import ", "from ")


def _categorize(module: str, project_root: Path) -> int:
    if module.startswith('.'):  # relative import
        return 2
    top = module.split('.')[0]
    if top in sys.stdlib_module_names:
        return 0
    if (project_root / f"{top}.py").exists() or (project_root / top).is_dir():
        return 2
    return 1


def _gather_imports(lines: list[str]) -> tuple[int, int, list[str]]:
    start = -1
    imports: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "from __future__ import annotations":
            continue
        if stripped.startswith(_IMPORT_RE):
            if start == -1:
                start = i
            imports.append(line.rstrip())
        elif start != -1:
            break
    end = start + len(imports) - 1
    return start, end, imports


def validate_import_sort(lines: list[str], path: Path, project_root: Path) -> list[str]:
    start, end, imports = _gather_imports(lines)
    if start == -1:
        return []
    desired = apply_fix_imports(lines, project_root, dry_run=True)
    if imports != desired:
        return [f"{path}:{start+1} imports not sorted"]
    return []


def apply_fix_imports(lines: list[str], project_root: Path, dry_run: bool = False) -> list[str]:
    start, end, imports = _gather_imports(lines)
    if start == -1:
        return imports if dry_run else False
    groups = {0: [], 1: [], 2: []}
    for line in imports:
        if line.startswith('from '):
            mod = line.split()[1]
        else:
            mod = line.split()[1]
        groups[_categorize(mod, project_root)].append(line)
    ordered: list[str] = []
    for g in (0, 1, 2):
        if groups[g]:
            if ordered:
                ordered.append('')
            ordered.extend(sorted(groups[g]))
    if dry_run:
        return ordered
    if imports == ordered:
        return False
    new_lines = lines[:start] + ordered + lines[end+1:]
    lines[:] = new_lines
    return True
