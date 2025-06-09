from __future__ import annotations

import re
from typing import Dict, Set

_CTRL_RE = re.compile(r'#\s*plint:\s*(disable|enable)=([A-Za-z0-9_-]+(?:,[A-Za-z0-9_-]+)*)')


def parse_controls(lines: list[str]) -> Dict[int, Set[str]]:
    active: Set[str] = set()
    result: Dict[int, Set[str]] = {}
    for i, line in enumerate(lines, start=1):
        m = _CTRL_RE.search(line)
        if m:
            action, rules = m.groups()
            names = {r.strip() for r in rules.split(',')}
            if action == 'disable':
                active.update(names)
            else:
                active.difference_update(names)
        result[i] = set(active)
    return result


def is_disabled(controls: Dict[int, Set[str]], rule: str, line: int) -> bool:
    for ln in range(line, 0, -1):
        if ln in controls:
            return rule in controls[ln]
    return False
